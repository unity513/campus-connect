"""Accounts: custom user, customer profiles, addresses, RBAC roles.

RBAC is enforced with Django's Groups + Permissions (server-side). The five
Campus Connect roles map to Groups; see accounts.roles.ROLE_DEFINITIONS.
"""
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """A single account model for both customers and back-office staff.

    `is_staff` grants access to the Django admin / back office. Customers have
    is_staff=False. Fine-grained back-office power comes from Group membership.
    """

    phone = models.CharField(max_length=32, blank=True)
    is_customer = models.BooleanField(default=True)
    # Marks accounts that completed age verification (for regulated products).
    age_verified = models.BooleanField(default=False)
    date_of_birth = models.DateField(null=True, blank=True)

    def role_names(self):
        return list(self.groups.values_list("name", flat=True))

    def has_role(self, name):
        return self.is_superuser or self.groups.filter(name=name).exists()


class CustomerProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    full_name = models.CharField(max_length=160, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    # Stored customer declarations (e.g. age / compliance acknowledgements).
    declarations = models.JSONField(default=dict, blank=True)
    marketing_opt_in = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.full_name or self.user.get_username()


class Address(models.Model):
    PICKUP = "pickup"
    DELIVERY = "delivery"
    KIND_CHOICES = [(PICKUP, "Pickup"), (DELIVERY, "Delivery")]

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addresses"
    )
    kind = models.CharField(max_length=12, choices=KIND_CHOICES, default=DELIVERY)
    label = models.CharField(max_length=80, blank=True)
    recipient = models.CharField(max_length=160, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    line1 = models.CharField(max_length=200, blank=True)
    line2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=120, blank=True)
    area = models.CharField(max_length=120, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "addresses"
        indexes = [models.Index(fields=["customer", "kind"])]

    def __str__(self):
        return f"{self.get_kind_display()} — {self.line1 or self.label}"
