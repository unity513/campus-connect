"""Orders, items, payments and payment proofs.

Order numbers look like CC-000001. Status transitions are tracked in
OrderStatusEvent. Payment proofs are stored in PRIVATE media and served only
through an authorization-checked view — never a predictable public URL.
"""
import uuid

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models, transaction

private_storage = FileSystemStorage(location=settings.PRIVATE_MEDIA_ROOT)


def proof_upload_path(instance, filename):
    # Unguessable path; the file is never served directly from here.
    token = uuid.uuid4().hex
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"proofs/{token}.{ext}"


class Order(models.Model):
    SUBMITTED = "submitted"
    PAYMENT_PENDING = "payment_pending"
    PROOF_UPLOADED = "proof_uploaded"
    PAYMENT_VERIFICATION = "payment_verification"
    PAYMENT_CONFIRMED = "payment_confirmed"
    PROCESSING = "processing"
    READY = "ready"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    PAYMENT_FAILED = "payment_failed"
    OUT_OF_STOCK = "out_of_stock"

    STATUS_CHOICES = [
        (SUBMITTED, "Order Submitted"),
        (PAYMENT_PENDING, "Payment Pending"),
        (PROOF_UPLOADED, "Payment Proof Uploaded"),
        (PAYMENT_VERIFICATION, "Payment Verification"),
        (PAYMENT_CONFIRMED, "Payment Confirmed"),
        (PROCESSING, "Processing"),
        (READY, "Ready for Fulfilment"),
        (FULFILLED, "Fulfilled"),
        (CANCELLED, "Cancelled"),
        (REJECTED, "Rejected"),
        (PAYMENT_FAILED, "Payment Failed"),
        (OUT_OF_STOCK, "Out of Stock"),
    ]

    # The main happy-path progression used by the step tracker.
    PROGRESS_FLOW = [
        SUBMITTED, PAYMENT_PENDING, PROOF_UPLOADED, PAYMENT_VERIFICATION,
        PAYMENT_CONFIRMED, PROCESSING, READY, FULFILLED,
    ]

    number = models.CharField(max_length=20, unique=True, editable=False)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="orders",
    )
    contact_name = models.CharField(max_length=160)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)

    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=SUBMITTED)

    payment_method = models.ForeignKey(
        "store.PaymentMethod", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="orders",
    )
    fulfilment_method = models.ForeignKey(
        "store.FulfilmentMethod", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="orders",
    )
    pickup_location = models.ForeignKey(
        "store.PickupLocation", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="orders",
    )
    delivery_address = models.ForeignKey(
        "accounts.Address", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="orders",
    )
    delivery_snapshot = models.JSONField(default=dict, blank=True)

    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=8, default="MWK")

    internal_notes = models.TextField(blank=True)
    stock_committed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["number"]),
            models.Index(fields=["customer", "-created_at"]),
        ]
        permissions = [
            ("verify_payment", "Can verify payments"),
            ("reject_payment", "Can reject payments"),
            ("update_fulfilment", "Can update fulfilment status"),
        ]

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = self._next_number()
        super().save(*args, **kwargs)

    @staticmethod
    def _next_number():
        with transaction.atomic():
            last = Order.objects.select_for_update().order_by("-id").first()
            seq = (last.id + 1) if last else 1
        return f"CC-{seq:06d}"

    @property
    def is_terminal(self):
        return self.status in (
            self.FULFILLED, self.CANCELLED, self.REJECTED, self.OUT_OF_STOCK
        )

    def progress_index(self):
        try:
            return self.PROGRESS_FLOW.index(self.status)
        except ValueError:
            return -1

    def progress_flow_labels(self):
        labels = dict(self.STATUS_CHOICES)
        return [(k, labels[k]) for k in self.PROGRESS_FLOW]

    def __str__(self):
        return self.number


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="items"
    )
    product = models.ForeignKey(
        "catalog.Product", null=True, on_delete=models.SET_NULL,
        related_name="order_items",
    )
    # Snapshot of product details at time of order (price locked in).
    product_name = models.CharField(max_length=200)
    sku = models.CharField(max_length=64, blank=True)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField()
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.quantity} x {self.product_name}"


class Payment(models.Model):
    PENDING = "pending"
    VERIFICATION = "verification"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    FAILED = "failed"
    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (VERIFICATION, "Awaiting Verification"),
        (CONFIRMED, "Confirmed"),
        (REJECTED, "Rejected"),
        (FAILED, "Failed"),
    ]

    order = models.OneToOneField(
        Order, on_delete=models.CASCADE, related_name="payment"
    )
    method = models.ForeignKey(
        "store.PaymentMethod", null=True, blank=True, on_delete=models.SET_NULL
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=PENDING)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reference = models.CharField(max_length=120, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="verified_payments",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payment[{self.get_status_display()}] for {self.order.number}"


class PaymentProof(models.Model):
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="proofs"
    )
    payment = models.ForeignKey(
        Payment, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="proofs",
    )
    file = models.FileField(upload_to=proof_upload_path, storage=private_storage)
    original_name = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=100, blank=True)
    size_bytes = models.PositiveIntegerField(default=0)
    reference = models.CharField(max_length=120, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="uploaded_proofs",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"Proof for {self.order.number}"


class OrderStatusEvent(models.Model):
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="status_events"
    )
    from_status = models.CharField(max_length=24, blank=True)
    to_status = models.CharField(max_length=24)
    note = models.CharField(max_length=255, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="order_changes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.order.number}: {self.from_status} -> {self.to_status}"
