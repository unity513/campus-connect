"""Secure first-run setup for Campus Connect.

Creates the RBAC roles, the first Super Admin (credentials from env or
prompted — never hard-coded in frontend), store/payment/merchant settings,
notification templates, and optional demo catalogue.

Usage:
    python manage.py savana_setup \
        --admin-username admin --admin-email you@example.com \
        --admin-password 'strong-pass' [--demo]

If password is omitted and running interactively you will be prompted.
"""
import os
from decimal import Decimal
from getpass import getpass

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts.models import CustomerProfile
from accounts.roles import SUPER_ADMIN, sync_roles
from catalog.models import Category, Product, ProductImage
from store.models import (
    FulfilmentMethod, MerchantProfile, NotificationTemplate, PaymentMethod,
    PickupLocation, StoreSetting,
)

User = get_user_model()

TEMPLATES = {
    "order_submitted": ("Your Campus Connect order {order_number} has been received",
        "Hi {customer_name},\n\nYour Campus Connect order {order_number} has been "
        "received. Please complete payment and upload your proof.\n\n— Campus Connect"),
    "proof_uploaded": ("Payment proof received for {order_number}",
        "Hi {customer_name},\n\nYour payment proof for {order_number} has been "
        "received and is awaiting verification.\n\n— Campus Connect"),
    "payment_confirmed": ("Payment verified for {order_number}",
        "Hi {customer_name},\n\nYour payment for {order_number} has been "
        "verified.\n\n— Campus Connect"),
    "payment_rejected": ("Payment could not be verified for {order_number}",
        "Hi {customer_name},\n\nWe could not verify your payment for "
        "{order_number}. Reason: {reason}\n\n— Campus Connect"),
    "order_processing": ("Your order {order_number} is being processed",
        "Hi {customer_name},\n\nYour order {order_number} is now being "
        "processed.\n\n— Campus Connect"),
    "order_ready": ("Your order {order_number} is ready",
        "Hi {customer_name},\n\nYour order {order_number} is ready for the "
        "next fulfilment step.\n\n— Campus Connect"),
    "order_completed": ("Your order {order_number} is complete",
        "Hi {customer_name},\n\nYour order {order_number} has been "
        "completed. Thank you for shopping with Campus Connect.\n\n— Campus Connect"),
}


class Command(BaseCommand):
    help = "Initial Campus Connect setup: roles, super admin, settings, templates."

    def add_arguments(self, parser):
        parser.add_argument("--admin-username", default=os.environ.get("SAVANA_ADMIN_USER"))
        parser.add_argument("--admin-email", default=os.environ.get("SAVANA_ADMIN_EMAIL", ""))
        parser.add_argument("--admin-password", default=os.environ.get("SAVANA_ADMIN_PASSWORD"))
        parser.add_argument("--demo", action="store_true",
                            help="Seed a small demo catalogue.")

    def handle(self, *args, **opts):
        sync_roles()
        self.stdout.write(self.style.SUCCESS("Roles synced."))
        self._settings()
        self._templates()
        self._payment_fulfilment()
        self._admin(opts)
        if opts["demo"]:
            self._demo()
        self.stdout.write(self.style.SUCCESS("Campus Connect setup complete."))

    def _settings(self):
        StoreSetting.set("store.name", "Campus Connect", "store", "Store name")
        StoreSetting.set("store.tagline",
                         "Simple products. Thoughtfully chosen.", "store",
                         "Tagline")
        StoreSetting.set("store.contact",
                         {"email": "hello@campusconnect.example",
                          "phone": "+265 000 000 000",
                          "hours": "Mon–Sat, 9am–5pm"}, "store", "Contact")
        StoreSetting.set("inventory.low_stock_threshold", 3, "inventory",
                         "Default low-stock threshold")
        StoreSetting.set("notifications.provider", "console", "notifications",
                         "Notification provider")
        StoreSetting.set("compliance.age_min", 18, "compliance",
                         "Default minimum age for age-restricted products")
        if not MerchantProfile.objects.exists():
            MerchantProfile.objects.create(
                name="Campus Connect Licensed Merchant",
                contact_email="merchant@campusconnect.example",
                license_info="Configure merchant license details in admin.",
                operating_info="Mon–Sat, 9am–5pm",
            )

    def _templates(self):
        for event, (subject, body) in TEMPLATES.items():
            NotificationTemplate.objects.update_or_create(
                event=event,
                defaults={"subject": subject, "body": body, "is_active": True},
            )

    def _payment_fulfilment(self):
        PaymentMethod.objects.get_or_create(
            slug="airtel-money",
            defaults={"name": "Airtel Money", "is_active": True,
                      "instructions": "Send payment to the Airtel Money number "
                      "below, then upload your confirmation message.",
                      "reference_hint": "Use your order number as reference.",
                      "account_name": "Configure in admin",
                      "account_number": "Configure in admin", "sort_order": 1})
        PaymentMethod.objects.get_or_create(
            slug="national-bank",
            defaults={"name": "National Bank", "is_active": True,
                      "instructions": "Make a bank transfer to the account "
                      "below, then upload your deposit slip.",
                      "reference_hint": "Use your order number as reference.",
                      "account_name": "Configure in admin",
                      "account_number": "Configure in admin", "sort_order": 2})
        FulfilmentMethod.objects.get_or_create(
            name="Store pickup", kind=FulfilmentMethod.PICKUP,
            defaults={"is_active": True, "fee": Decimal("0"), "sort_order": 1})
        FulfilmentMethod.objects.get_or_create(
            name="Local delivery", kind=FulfilmentMethod.DELIVERY,
            defaults={"is_active": True, "fee": Decimal("2500"), "sort_order": 2,
                      "delivery_areas": "City centre, suburbs"})
        PickupLocation.objects.get_or_create(
            name="Campus Connect Pickup Point",
            defaults={"address": "Configure address in admin",
                      "hours": "Mon–Sat, 9am–5pm", "is_active": True})

    def _admin(self, opts):
        username = opts.get("admin_username")
        if not username:
            self.stdout.write(self.style.WARNING(
                "No admin username provided; skipping super admin creation. "
                "Re-run with --admin-username to create one."))
            return
        if User.objects.filter(username=username).exists():
            self.stdout.write(f"Super admin '{username}' already exists.")
            return
        password = opts.get("admin_password")
        if not password:
            try:
                password = getpass("Super admin password: ")
            except Exception:
                self.stdout.write(self.style.ERROR(
                    "Password required (set --admin-password or SAVANA_ADMIN_PASSWORD)."))
                return
        user = User.objects.create_superuser(
            username=username, email=opts.get("admin_email", ""),
            password=password)
        user.is_customer = False
        user.save(update_fields=["is_customer"])
        from django.contrib.auth.models import Group
        user.groups.add(Group.objects.get(name=SUPER_ADMIN))
        self.stdout.write(self.style.SUCCESS(f"Super admin '{username}' created."))

    def _demo(self):
        home, _ = Category.objects.get_or_create(name="Home")
        care, _ = Category.objects.get_or_create(name="Everyday Care")
        bags, _ = Category.objects.get_or_create(name="Bags")
        demo = [
            ("Botanical Everyday Oil", "CC-OIL-001", care, 18500, 12,
             "A simple botanical oil for everyday care.",
             "https://images.pexels.com/photos/7797453/pexels-photo-7797453.jpeg"),
            ("Textured Market Tote", "CC-TOTE-001", bags, 24000, 8,
             "A relaxed carryall with a natural texture.",
             "https://images.pexels.com/photos/12025443/pexels-photo-12025443.jpeg"),
            ("Ceramic Tumbler", "CC-TUM-001", home, 16000, 2,
             "A softly finished cup for daily rituals.",
             "https://images.pexels.com/photos/6213674/pexels-photo-6213674.jpeg"),
            ("Linen Travel Pouch", "CC-POU-001", bags, 13500, 20,
             "A lightweight home for the little essentials.",
             "https://images.pexels.com/photos/4856502/pexels-photo-4856502.jpeg"),
        ]
        for name, sku, cat, price, stock, desc, img in demo:
            product, created = Product.objects.get_or_create(
                sku=sku,
                defaults={"name": name, "category": cat,
                          "price": Decimal(price), "stock_quantity": stock,
                          "short_description": desc, "description": desc,
                          "status": Product.PUBLISHED, "is_featured": True})
            if created:
                ProductImage.objects.create(product=product, external_url=img,
                                            alt_text=name)
        self.stdout.write(self.style.SUCCESS("Demo catalogue seeded."))
