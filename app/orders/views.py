"""Checkout, order tracking, payment-proof upload, and private proof serving."""
import os

from django.conf import settings
from django.contrib import messages
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from catalog.services import InsufficientStock
from store.models import FulfilmentMethod, PaymentMethod, PickupLocation
from store.services import track

from .models import Order, PaymentProof
from .services import Cart, place_order, record_proof_uploaded


def checkout(request):
    cart = Cart(request)
    rows = cart.items()
    if not rows:
        messages.info(request, "Your cart is empty.")
        return redirect("storefront:shop")

    payment_methods = PaymentMethod.objects.filter(is_active=True)
    fulfilment_methods = FulfilmentMethod.objects.filter(is_active=True)
    pickup_locations = PickupLocation.objects.filter(is_active=True)

    if request.method == "POST":
        problems = cart.validate_stock()
        if problems:
            for p in problems:
                messages.error(request, p)
            return redirect("storefront:cart")

        pm = get_object_or_404(
            PaymentMethod, pk=request.POST.get("payment_method"),
            is_active=True,
        )
        fm = get_object_or_404(
            FulfilmentMethod, pk=request.POST.get("fulfilment_method"),
            is_active=True,
        )
        pickup = None
        delivery_snapshot = {}
        if fm.kind == FulfilmentMethod.PICKUP:
            pickup = get_object_or_404(
                PickupLocation, pk=request.POST.get("pickup_location"),
                is_active=True,
            )
        else:
            delivery_snapshot = {
                "recipient": request.POST.get("recipient", "").strip(),
                "phone": request.POST.get("delivery_phone", "").strip(),
                "line1": request.POST.get("line1", "").strip(),
                "city": request.POST.get("city", "").strip(),
                "area": request.POST.get("area", "").strip(),
                "notes": request.POST.get("delivery_notes", "").strip(),
            }
            if not delivery_snapshot["line1"]:
                messages.error(request, "Please provide a delivery address.")
                return redirect("orders:checkout")

        contact = {
            "name": request.POST.get("contact_name", "").strip()
            or (request.user.get_full_name() if request.user.is_authenticated else ""),
            "email": request.POST.get("contact_email", "").strip()
            or (request.user.email if request.user.is_authenticated else ""),
            "phone": request.POST.get("contact_phone", "").strip(),
        }
        if not contact["name"]:
            messages.error(request, "Please provide a contact name.")
            return redirect("orders:checkout")

        try:
            order = place_order(
                request, cart, contact=contact, payment_method=pm,
                fulfilment_method=fm, pickup_location=pickup,
                delivery_snapshot=delivery_snapshot,
            )
        except InsufficientStock as exc:
            messages.error(request, str(exc))
            return redirect("storefront:cart")

        track("order_submitted", request, order_number=order.number)
        request.session["last_order"] = order.number
        return redirect("orders:instructions", number=order.number)

    return render(request, "orders/checkout.html", {
        "rows": rows,
        "subtotal": cart.subtotal,
        "payment_methods": payment_methods,
        "fulfilment_methods": fulfilment_methods,
        "pickup_locations": pickup_locations,
    })


def _can_view_order(request, order):
    if order.customer and request.user.is_authenticated:
        if order.customer_id == request.user.id or request.user.is_staff:
            return True
    # Guest orders: allow if the order number is the session's last order.
    return request.session.get("last_order") == order.number or (
        request.user.is_authenticated and request.user.is_staff
    )


def instructions(request, number):
    order = get_object_or_404(Order, number=number)
    if not _can_view_order(request, order):
        return HttpResponseForbidden("You are not authorised to view this order.")
    return render(request, "orders/instructions.html", {"order": order})


def track_order(request, number):
    order = get_object_or_404(Order, number=number)
    if not _can_view_order(request, order):
        return HttpResponseForbidden("You are not authorised to view this order.")
    return render(request, "orders/track.html", {"order": order})


def track_lookup(request):
    """Public lookup by order number (still checks session/ownership)."""
    number = request.GET.get("number", "").strip()
    if number:
        return redirect("orders:track", number=number)
    return render(request, "orders/track_lookup.html")


@require_POST
def upload_proof(request, number):
    order = get_object_or_404(Order, number=number)
    if not _can_view_order(request, order):
        return HttpResponseForbidden("Not authorised.")

    upload = request.FILES.get("proof")
    if not upload:
        messages.error(request, "Please choose a file to upload.")
        return redirect("orders:instructions", number=number)

    # Validate size and extension server-side.
    ext = os.path.splitext(upload.name)[1].lower()
    if ext not in settings.ALLOWED_PROOF_EXTENSIONS:
        messages.error(
            request,
            "Unsupported file type. Allowed: "
            + ", ".join(sorted(settings.ALLOWED_PROOF_EXTENSIONS)),
        )
        return redirect("orders:instructions", number=number)
    if upload.size > settings.MAX_UPLOAD_BYTES:
        messages.error(request, "File is too large.")
        return redirect("orders:instructions", number=number)

    proof = PaymentProof.objects.create(
        order=order,
        payment=getattr(order, "payment", None),
        file=upload,
        original_name=upload.name[:255],
        content_type=upload.content_type or "",
        size_bytes=upload.size,
        reference=request.POST.get("reference", "").strip(),
        uploaded_by=request.user if request.user.is_authenticated else None,
    )
    record_proof_uploaded(order, user=request.user)
    track("payment_proof_uploaded", request, order_number=order.number)
    messages.success(
        request,
        "Your payment proof has been received and is awaiting verification.",
    )
    return redirect("orders:track", number=number)


def serve_proof(request, pk):
    """Serve a payment proof ONLY to authorised staff or the order owner.
    Files live in private storage and are never publicly addressable."""
    proof = get_object_or_404(PaymentProof, pk=pk)
    order = proof.order
    allowed = False
    if request.user.is_authenticated:
        if request.user.is_staff or (
            order.customer_id and order.customer_id == request.user.id
        ):
            allowed = True
    if not allowed:
        return HttpResponseForbidden("Not authorised.")
    if not proof.file or not os.path.exists(proof.file.path):
        raise Http404("File not found.")
    return FileResponse(open(proof.file.path, "rb"), as_attachment=False,
                        filename=proof.original_name or "proof")
