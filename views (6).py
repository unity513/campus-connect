"""Branded back-office dashboard. Complements the Django admin with a
Campus Connect-styled operations view. All actions are permission-checked server-side.
"""
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from catalog.models import InventoryMovement, Product
from catalog.services import InsufficientStock, adjust_stock, set_stock
from orders.models import Order, PaymentProof
from orders.services import (
    cancel_order, confirm_payment, reject_payment, update_fulfilment,
)
from store.models import AuditLog
from store.services import audit


def staff_required(view):
    return login_required(
        user_passes_test(lambda u: u.is_staff, login_url="accounts:login")(view)
    )


def _perm(user, codename):
    return user.is_superuser or user.has_perm(codename)


@staff_required
def dashboard(request):
    days = int(request.GET.get("days", 30))
    since = timezone.now() - timedelta(days=days)
    orders = Order.objects.all()
    recent = orders.filter(created_at__gte=since)

    status_counts = {
        row["status"]: row["n"]
        for row in orders.values("status").annotate(n=Count("id"))
    }

    context = {
        "days": days,
        "total_orders": orders.count(),
        "pending_payments": status_counts.get(Order.PAYMENT_PENDING, 0),
        "awaiting_verification": status_counts.get(
            Order.PAYMENT_VERIFICATION, 0),
        "confirmed": status_counts.get(Order.PAYMENT_CONFIRMED, 0),
        "processing": status_counts.get(Order.PROCESSING, 0),
        "completed": status_counts.get(Order.FULFILLED, 0),
        "cancelled": status_counts.get(Order.CANCELLED, 0),
        "revenue": recent.filter(
            status__in=[Order.PAYMENT_CONFIRMED, Order.PROCESSING,
                        Order.READY, Order.FULFILLED]
        ).aggregate(s=Sum("total"))["s"] or 0,
        "recent_orders": orders.select_related("payment_method")[:10],
        "recent_proofs": PaymentProof.objects.select_related("order")[:10],
        "low_stock": _low_stock(),
        "out_of_stock": Product.objects.filter(stock_quantity=0).count(),
        "total_products": Product.objects.count(),
    }
    return render(request, "backoffice/dashboard.html", context)


def _low_stock():
    from django.db.models import F
    return Product.objects.filter(
        stock_quantity__gt=0,
        stock_quantity__lte=F("low_stock_threshold"),
    )[:10]


@staff_required
def order_list(request):
    status = request.GET.get("status", "")
    orders = Order.objects.select_related("payment_method").all()
    if status:
        orders = orders.filter(status=status)
    return render(request, "backoffice/order_list.html", {
        "orders": orders[:200],
        "status": status,
        "status_choices": Order.STATUS_CHOICES,
    })


@staff_required
def order_detail(request, number):
    order = get_object_or_404(
        Order.objects.select_related("payment", "payment_method",
                                     "fulfilment_method", "pickup_location"),
        number=number,
    )
    return render(request, "backoffice/order_detail.html", {
        "order": order,
        "items": order.items.all(),
        "proofs": order.proofs.all(),
        "events": order.status_events.all(),
        "can_verify": _perm(request.user, "orders.verify_payment"),
        "can_reject": _perm(request.user, "orders.reject_payment"),
        "can_fulfil": _perm(request.user, "orders.update_fulfilment"),
        "fulfil_choices": [
            (Order.PROCESSING, "Processing"),
            (Order.READY, "Ready for Fulfilment"),
            (Order.FULFILLED, "Fulfilled"),
        ],
    }) 


@staff_required
@require_POST
def order_action(request, number):
    order = get_object_or_404(Order, number=number)
    action = request.POST.get("action")

    if action == "verify":
        if not _perm(request.user, "orders.verify_payment"):
            return _forbidden(request, number)
        confirm_payment(order, request.user)
        messages.success(request, f"Payment confirmed for {order.number}.")
    elif action == "reject":
        if not _perm(request.user, "orders.reject_payment"):
            return _forbidden(request, number)
        reason = request.POST.get("reason", "").strip()
        if not reason:
            messages.error(request, "A rejection reason is required.")
        else:
            reject_payment(order, request.user, reason)
            messages.success(request, f"Payment rejected for {order.number}.")
    elif action == "fulfil":
        if not _perm(request.user, "orders.update_fulfilment"):
            return _forbidden(request, number)
        to_status = request.POST.get("to_status")
        if to_status in dict(Order.STATUS_CHOICES):
            update_fulfilment(order, to_status, request.user)
            messages.success(request, "Fulfilment status updated.")
    elif action == "cancel":
        if not request.user.has_perm("orders.change_order") and not request.user.is_superuser:
            return _forbidden(request, number)
        cancel_order(order, request.user, request.POST.get("reason", ""))
        messages.success(request, f"Order {order.number} cancelled.")
    elif action == "note":
        note = request.POST.get("note", "").strip()
        if note:
            order.internal_notes = (order.internal_notes + "\n" + note).strip()
            order.save(update_fields=["internal_notes"])
            audit(request.user, "note_added", order, order_number=order.number)
            messages.success(request, "Internal note added.")
    return redirect("backoffice:order_detail", number=number)


def _forbidden(request, number):
    messages.error(request, "Your role does not permit that action.")
    return redirect("backoffice:order_detail", number=number)


@staff_required
def inventory(request):
    products = Product.objects.select_related("category").order_by("name")
    return render(request, "backoffice/inventory.html", {
        "products": products,
        "movements": InventoryMovement.objects.select_related(
            "product", "created_by")[:30],
    })


@staff_required
@require_POST
def inventory_adjust(request):
    if not (_perm(request.user, "catalog.change_product")):
        messages.error(request, "Your role does not permit stock changes.")
        return redirect("backoffice:inventory")
    product = get_object_or_404(Product, pk=request.POST.get("product_id"))
    mode = request.POST.get("mode")
    note = request.POST.get("note", "").strip()
    try:
        amount = int(request.POST.get("amount", 0))
    except ValueError:
        amount = 0
    try:
        if mode == "increase":
            adjust_stock(product, abs(amount), InventoryMovement.INCREASE,
                         user=request.user, note=note)
        elif mode == "decrease":
            adjust_stock(product, -abs(amount), InventoryMovement.DECREASE,
                         user=request.user, note=note)
        elif mode == "set":
            set_stock(product, max(0, amount), user=request.user, note=note)
        audit(request.user, "stock_changed", product, mode=mode, amount=amount)
        messages.success(request, f"Stock updated for {product.name}.")
    except InsufficientStock as exc:
        messages.error(request, str(exc))
    return redirect("backoffice:inventory")


@staff_required
def audit_log(request):
    if not request.user.is_superuser and not request.user.has_perm("store.view_auditlog"):
        messages.error(request, "Not authorised to view the audit log.")
        return redirect("backoffice:dashboard")
    return render(request, "backoffice/audit.html", {
        "entries": AuditLog.objects.select_related("user")[:200],
    })
