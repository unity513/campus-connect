"""Store configuration: settings, payment methods, fulfilment, merchant
profile, notification templates, audit log, analytics events.

Nothing operational is hard-coded in templates — account numbers, payment
instructions, pickup locations, delivery fees and store info all live here
and are editable from the back office.
"""
from django.conf import settings
from django.db import models


class StoreSetting(models.Model):
    """Key/value store for store-wide configuration. Grouped for the UI."""

    key = models.CharField(max_length=100, unique=True)
    value = models.JSONField(default=dict, blank=True)
    group = models.CharField(max_length=40, default="store")
    label = models.CharField(max_length=160, blank=True)

    class Meta:
        ordering = ["group", "key"]

    def __str__(self):
        return self.key

    @classmethod
    def get(cls, key, default=None):
        try:
            return cls.objects.get(key=key).value
        except cls.DoesNotExist:
            return default

    @classmethod
    def set(cls, key, value, group="store", label=""):
        obj, _ = cls.objects.update_or_create(
            key=key, defaults={"value": value, "group": group, "label": label}
        )
        return obj


class PaymentMethod(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    is_active = models.BooleanField(default=True)
    # Instructions + account details configured by admin, never in frontend.
    instructions = models.TextField(
        blank=True, help_text="Shown to the customer after order submission."
    )
    account_name = models.CharField(max_length=160, blank=True)
    account_number = models.CharField(max_length=120, blank=True)
    reference_hint = models.CharField(
        max_length=200, blank=True,
        help_text="e.g. 'Use your order number as the reference.'",
    )
    requires_proof = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class PickupLocation(models.Model):
    name = models.CharField(max_length=160)
    address = models.CharField(max_length=255, blank=True)
    hours = models.CharField(max_length=160, blank=True)
    instructions = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class FulfilmentMethod(models.Model):
    PICKUP = "pickup"
    DELIVERY = "delivery"
    KIND_CHOICES = [(PICKUP, "Pickup"), (DELIVERY, "Delivery")]

    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=12, choices=KIND_CHOICES)
    is_active = models.BooleanField(default=True)
    fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_areas = models.TextField(
        blank=True, help_text="Comma or newline separated serviceable areas."
    )
    instructions = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()})"


class MerchantProfile(models.Model):
    """The licensed merchant that fulfils regulated transactions. Campus Connect is
    the storefront technology; the merchant is the licensed entity."""

    name = models.CharField(max_length=200)
    contact_name = models.CharField(max_length=160, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)
    license_info = models.TextField(blank=True)
    operating_info = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    supported_categories = models.ManyToManyField(
        "catalog.Category", blank=True, related_name="merchants"
    )
    payment_methods = models.ManyToManyField(PaymentMethod, blank=True)
    fulfilment_methods = models.ManyToManyField(FulfilmentMethod, blank=True)
    pickup_locations = models.ManyToManyField(PickupLocation, blank=True)

    def __str__(self):
        return self.name


class NotificationTemplate(models.Model):
    event = models.CharField(max_length=60, unique=True)
    subject = models.CharField(max_length=200)
    body = models.TextField(
        help_text="Supports {order_number}, {customer_name}, {status}."
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.event


class Notification(models.Model):
    """A dispatched notification record (in-app + whatever provider sends)."""

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="notifications",
    )
    event = models.CharField(max_length=60)
    subject = models.CharField(max_length=200)
    body = models.TextField()
    order_number = models.CharField(max_length=40, blank=True)
    is_read = models.BooleanField(default=False)
    provider = models.CharField(max_length=40, default="console")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "is_read"])]

    def __str__(self):
        return f"{self.event} -> {self.recipient}"


class AuditLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="audit_entries",
    )
    action = models.CharField(max_length=80)
    object_type = models.CharField(max_length=80, blank=True)
    object_id = models.CharField(max_length=80, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["action", "created_at"])]

    def __str__(self):
        return f"{self.action} by {self.user} @ {self.created_at:%Y-%m-%d %H:%M}"


class AnalyticsEvent(models.Model):
    """Minimal first-party analytics. No unnecessary PII is stored."""

    name = models.CharField(max_length=60)
    properties = models.JSONField(default=dict, blank=True)
    session_key = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["name", "created_at"])]

    def __str__(self):
        return self.name
