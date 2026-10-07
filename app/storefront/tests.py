"""Integration tests covering the Campus Connect acceptance criteria. Run with:
    python manage.py test
"""
from decimal import Decimal

from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from accounts.models import User
from accounts.roles import sync_roles
from catalog.models import Category, ComplianceRecord, Product
from orders.models import Order, PaymentProof
from store.models import (
    AuditLog, FulfilmentMethod, NotificationTemplate, PaymentMethod,
    PickupLocation,
)


def _seed():
    sync_roles()
    cat = Category.objects.create(name="Home")
    oil = Product.objects.create(
        name="Everyday Oil", sku="CC-OIL-001", category=cat,
        price=Decimal("18500"), stock_quantity=12, status=Product.PUBLISHED,
        is_featured=True, short_description="A simple oil.")
    tumbler = Product.objects.create(
        name="Ceramic Tumbler", sku="CC-TUM-001", category=cat,
        price=Decimal("16000"), stock_quantity=2, status=Product.PUBLISHED)
    pm = PaymentMethod.objects.create(name="Airtel Money", slug="airtel-money",
                                      is_active=True, instructions="Pay here.")
    fm = FulfilmentMethod.objects.create(name="Store pickup",
                                         kind=FulfilmentMethod.PICKUP, is_active=True)
    loc = PickupLocation.objects.create(name="Pickup", is_active=True)
    for ev in ["order_submitted", "proof_uploaded", "payment_confirmed",
               "payment_rejected", "order_processing", "order_ready",
               "order_completed"]:
        NotificationTemplate.objects.create(event=ev, subject="S {order_number}",
                                            body="B {order_number}")
    return cat, oil, tumbler, pm, fm, loc


@override_settings(ALLOWED_HOSTS=["testserver"])
class SavanaAcceptanceTests(TestCase):
    def setUp(self):
        self.cat, self.oil, self.tumbler, self.pm, self.fm, self.loc = _seed()
        self.admin = User.objects.create_superuser("admin", "a@b.c", "pw-strong-123")

    def _place_order(self, client, product, qty):
        client.post("/cart/add/", {"product_id": product.id, "quantity": qty})
        client.post("/orders/checkout/", {
            "payment_method": self.pm.id, "fulfilment_method": self.fm.id,
            "pickup_location": self.loc.id, "contact_name": "Buyer",
            "contact_email": "b@e.com", "contact_phone": "+265"})
        return Order.objects.order_by("-id").first()

    def test_storefront_pages(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/shop/").status_code, 200)
        self.assertContains(self.client.get("/shop/"), "Everyday Oil")
        self.assertEqual(self.client.get(f"/product/{self.oil.slug}/").status_code, 200)

    def test_cart_stock_guard(self):
        self.client.post("/cart/add/", {"product_id": self.tumbler.id, "quantity": 99})
        qty = self.client.session.get("cart", {}).get(str(self.tumbler.id), 0)
        self.assertLessEqual(qty, self.tumbler.stock_quantity)

    def test_full_order_and_payment_flow(self):
        order = self._place_order(self.client, self.oil, 3)
        self.assertTrue(order.number.startswith("CC-"))
        self.assertEqual(order.status, Order.PAYMENT_PENDING)
        proof = SimpleUploadedFile("p.png", b"\x89PNG\r\n\x1a\n0000", content_type="image/png")
        self.client.post(f"/orders/{order.number}/proof/", {"proof": proof})
        order.refresh_from_db()
        self.assertEqual(order.status, Order.PAYMENT_VERIFICATION)
        p = PaymentProof.objects.get(order=order)
        self.assertIn("private_media", p.file.path)
        # anonymous cannot fetch proof
        self.assertEqual(self.client.get(f"/orders/proof/{p.pk}/file/").status_code, 403)
        # admin confirms -> inventory decrements
        self.client.force_login(self.admin)
        before = Product.objects.get(pk=self.oil.pk).stock_quantity
        self.client.post(f"/backoffice/orders/{order.number}/action/", {"action": "verify"})
        order.refresh_from_db()
        self.assertEqual(order.status, Order.PROCESSING)
        self.assertEqual(Product.objects.get(pk=self.oil.pk).stock_quantity, before - 3)

    def test_reject_requires_reason(self):
        order = self._place_order(self.client, self.oil, 1)
        self.client.force_login(self.admin)
        self.client.post(f"/backoffice/orders/{order.number}/action/", {"action": "reject", "reason": ""})
        order.refresh_from_db()
        self.assertNotEqual(order.status, Order.REJECTED)
        self.client.post(f"/backoffice/orders/{order.number}/action/", {"action": "reject", "reason": "Mismatch"})
        order.refresh_from_db()
        self.assertEqual(order.status, Order.REJECTED)
        self.assertTrue(AuditLog.objects.filter(action="payment_rejected").exists())

    def test_product_publish_lifecycle(self):
        p = Product.objects.create(name="Widget", sku="CC-W-1", category=self.cat,
                                   price=Decimal("5000"), stock_quantity=5, status=Product.DRAFT)
        self.assertEqual(self.client.get(f"/product/{p.slug}/").status_code, 404)
        p.status = Product.PUBLISHED; p.save()
        self.assertEqual(self.client.get(f"/product/{p.slug}/").status_code, 200)
        p.status = Product.UNPUBLISHED; p.save()
        self.assertEqual(self.client.get(f"/product/{p.slug}/").status_code, 404)

    def test_regulated_product_gating(self):
        reg = Product.objects.create(name="Reg", sku="CC-R-1", category=self.cat,
                                     price=Decimal("9000"), stock_quantity=10,
                                     status=Product.PUBLISHED,
                                     regulatory_classification=Product.REGULATED)
        self.assertFalse(reg.is_transactable())
        ComplianceRecord.objects.create(product=reg, status=ComplianceRecord.APPROVED)
        self.assertTrue(Product.objects.get(pk=reg.pk).is_transactable())

    def test_rbac_server_side(self):
        v = User.objects.create_user("ver", password="pw-strong-123", is_staff=True)
        v.groups.add(Group.objects.get(name="Payment Verifier"))
        self.assertTrue(v.has_perm("orders.verify_payment"))
        f = User.objects.create_user("ful", password="pw-strong-123", is_staff=True)
        f.groups.add(Group.objects.get(name="Fulfilment Staff"))
        self.assertFalse(f.has_perm("orders.verify_payment"))

    def test_inventory_status_flip(self):
        self.client.force_login(self.admin)
        self.client.post("/backoffice/inventory/adjust/",
                         {"product_id": self.tumbler.id, "mode": "set", "amount": 0})
        self.assertEqual(Product.objects.get(pk=self.tumbler.pk).status, Product.OUT_OF_STOCK)
        self.client.post("/backoffice/inventory/adjust/",
                         {"product_id": self.tumbler.id, "mode": "increase", "amount": 4})
        t = Product.objects.get(pk=self.tumbler.pk)
        self.assertEqual(t.status, Product.PUBLISHED)
        self.assertEqual(t.stock_quantity, 4)

    def test_seo_endpoints(self):
        self.assertEqual(self.client.get("/sitemap.xml").status_code, 200)
        self.assertContains(self.client.get("/robots.txt"), "Sitemap")

    def test_negative_inventory_prevented(self):
        from catalog.services import InsufficientStock, adjust_stock
        from catalog.models import InventoryMovement
        with self.assertRaises(InsufficientStock):
            adjust_stock(self.tumbler, -999, InventoryMovement.DECREASE)
