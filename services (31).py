"""Order + cart + payment workflow services.

The cart lives in the session. Stock is validated at add-time and again at
order submission. Inventory is only committed when payment is confirmed
(the configured business workflow), never when a proof is merely uploaded.
"""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from catalog.models import InventoryMovement, Product
from catalog.services import InsufficientStock, adjust_stock
from store.services import audit, notify

from .models import Order, OrderItem, OrderStatusEvent, Payment

CART_SESSION_KEY = "cart"


class Cart:
    """Session-backed cart. Stores {product_id: quantity}."""

    def __init__(self, request):
        self.session = request.session
        self.data = self.session.setdefault(CART_SESSION_KEY, {})

    def _save(self):
        self.session[CART_SESSION_KEY] = self.data
        self.session.modified = True

    def add(self, product, quantity=1):
        if not product.is_transactable():
            raise InsufficientStock("This product is not available to order.")
        current = self.data.get(str(product.id), 0)
        desired = current + quantity
        if desired > product.stock_quantity:
            raise InsufficientStock(
                f"Only {product.stock_quantity} of {product.name} available."
            )
        self.data[str(product.id)] = desired
        self._save()

    def set_quantity(self, product, quantity):
        if quantity <= 0:
            self.remove(product)
            return
        if quantity > product.stock_quantity:
            raise InsufficientStock(
                f"Only {product.stock_quantity} of {product.name} available."
            )
        self.data[str(product.id)] = quantity
        self._save()

    def remove(self, product):
        self.data.pop(str(product.id), None)
        self._save()

    def clear(self):
        self.data = {}
        self._save()

    def items(self):
        ids = [int(i) for i in self.data.keys()]
        products = {p.id: p for p in Product.objects.filter(id__in=ids)}
        rows = []
        for pid_str, qty in self.data.items():
            product = products.get(int(pid_str))
            if not product:
                continue
            line_total = product.effective_price * qty
            rows.append({
                "product": product,
                "quantity": qty,
                "unit_price": product.effective_price,
                "line_total": line_total,
            })
        return rows

    @property
    def count(self):
        return sum(self.data.values())

    @property
    def subtotal(self):
        return sum((r["line_total"] for r in self.items()), Decimal("0"))

    def validate_stock(self):
        """Return a list of problems; empty list means ok."""
        problems = []
        for row in self.items():
            p = row["product"]
            if not p.is_transactable():
                problems.append(f"{p.name} is no longer available.")
            elif row["quantity"] > p.stock_quantity:
                problems.append(
                    f"Only {p.stock_quantity} of {p.name} remain in stock."
                )
        return problems


@transaction.atomic
def place_order(request, cart, *, contact, payment_method, fulfilment_method,
                pickup_location=None, delivery_snapshot=None):
    """Create an Order from the cart after re-validating stock."""
    problems = cart.validate_stock()
    if problems:
        raise InsufficientStock(" ".join(problems))

    rows = cart.items()
    if not rows:
        raise InsufficientStock("Your cart is empty.")

    subtotal = sum((r["line_total"] for r in rows), Decimal("0"))
    fee = fulfilment_method.fee if fulfilment_method else Decimal("0")
    total = subtotal + fee

    order = Order.objects.create(
        customer=request.user if request.user.is_authenticated else None,
        contact_name=contact["name"],
        contact_email=contact.get("email", ""),
        contact_phone=contact.get("phone", ""),
        status=Order.PAYMENT_PENDING,
        payment_method=payment_method,
        fulfilment_method=fulfilment_method,
        pickup_location=pickup_location,
        delivery_snapshot=delivery_snapshot or {},
        subtotal=subtotal,
        delivery_fee=fee,
        total=total,
    )
    for r in rows:
        p = r["product"]
        OrderItem.objects.create(
            order=order, product=p, product_name=p.name, sku=p.sku,
            unit_price=r["unit_price"], quantity=r["quantity"],
            line_total=r["line_total"],
        )
    Payment.objects.create(
        order=order, method=payment_method, amount=total,
        status=Payment.PENDING,
    )
    OrderStatusEvent.objects.create(
        order=order, from_status="", to_status=Order.SUBMITTED,
        note="Order submitted.",
    )
    OrderStatusEvent.objects.create(
        order=order, from_status=Order.SUBMITTED, to_status=Order.PAYMENT_PENDING,
        note="Awaiting payment.",
    )
    cart.clear()
    notify(
        "order_submitted", recipient=order.customer, order_number=order.number,
        context={
            "order_number": order.number, "customer_name": order.contact_name,
            "status": order.get_status_display(),
        },
    )
    return order


def transition(order, to_status, *, user=None, note=""):
    """Move an order to a new status, recording the event."""
    frm = order.status
    order.status = to_status
    order.save(update_fields=["status", "updated_at"])
    OrderStatusEvent.objects.create(
        order=order, from_status=frm, to_status=to_status, note=note,
        changed_by=user if (user and user.is_authenticated) else None,
    )
    return order


@transaction.atomic
def record_proof_uploaded(order, user=None):
    payment = order.payment
    payment.status = Payment.VERIFICATION
    payment.save(update_fields=["status", "updated_at"])
    transition(order, Order.PAYMENT_VERIFICATION, user=user,
               note="Payment proof uploaded; awaiting verification.")
    notify(
        "proof_uploaded", recipient=order.customer, order_number=order.number,
        context={"order_number": order.number,
                 "customer_name": order.contact_name,
                 "status": order.get_status_display()},
    )


@transaction.atomic
def confirm_payment(order, user):
    """Confirm payment, commit inventory, advance the order. Admin-only."""
    payment = order.payment
    payment.status = Payment.CONFIRMED
    payment.verified_by = user
    payment.verified_at = timezone.now()
    payment.save()

    # Commit inventory exactly once.
    if not order.stock_committed:
        for item in order.items.select_related("product"):
            if item.product:
                adjust_stock(
                    item.product, -item.quantity, InventoryMovement.SALE,
                    user=user, note=f"Order {order.number}",
                )
        order.stock_committed = True
        order.save(update_fields=["stock_committed"])

    transition(order, Order.PAYMENT_CONFIRMED, user=user,
               note="Payment verified and confirmed.")
    transition(order, Order.PROCESSING, user=user,
               note="Order moved to processing.")
    audit(user, "payment_verified", order, order_number=order.number)
    notify("payment_confirmed", recipient=order.customer,
           order_number=order.number,
           context={"order_number": order.number,
                    "customer_name": order.contact_name,
                    "status": order.get_status_display()})
    notify("order_processing", recipient=order.customer,
           order_number=order.number,
           context={"order_number": order.number,
                    "customer_name": order.contact_name,
                    "status": "Processing"})
    return order


@transaction.atomic
def reject_payment(order, user, reason):
    if not reason:
        raise ValueError("A rejection reason is required.")
    payment = order.payment
    payment.status = Payment.REJECTED
    payment.rejection_reason = reason
    payment.verified_by = user
    payment.verified_at = timezone.now()
    payment.save()
    transition(order, Order.REJECTED, user=user,
               note=f"Payment rejected: {reason}")
    audit(user, "payment_rejected", order, order_number=order.number,
          reason=reason)
    notify("payment_rejected", recipient=order.customer,
           order_number=order.number,
           context={"order_number": order.number,
                    "customer_name": order.contact_name,
                    "status": order.get_status_display(), "reason": reason})
    return order


@transaction.atomic
def update_fulfilment(order, to_status, user):
    transition(order, to_status, user=user,
               note=f"Fulfilment status set to {dict(Order.STATUS_CHOICES)[to_status]}.")
    audit(user, "fulfilment_updated", order, order_number=order.number,
          status=to_status)
    event = {
        Order.READY: "order_ready",
        Order.FULFILLED: "order_completed",
    }.get(to_status)
    if event:
        notify(event, recipient=order.customer, order_number=order.number,
               context={"order_number": order.number,
                        "customer_name": order.contact_name,
                        "status": order.get_status_display()})
    return order


@transaction.atomic
def cancel_order(order, user, reason=""):
    # Return committed stock if the order had reserved it.
    if order.stock_committed:
        for item in order.items.select_related("product"):
            if item.product:
                adjust_stock(item.product, item.quantity,
                             InventoryMovement.CORRECTION, user=user,
                             note=f"Cancelled {order.number}")
        order.stock_committed = False
        order.save(update_fields=["stock_committed"])
    transition(order, Order.CANCELLED, user=user,
               note=f"Order cancelled. {reason}".strip())
    audit(user, "order_cancelled", order, order_number=order.number,
          reason=reason)
    return order
