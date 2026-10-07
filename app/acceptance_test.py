"""End-to-end acceptance test for Campus Connect — exercises the real DB-backed flows
(customer journey, admin journey, product lifecycle, inventory, verify/reject).
Run with:  python manage.py shell < acceptance_test.py
"""
from decimal import Decimal
from django.test import Client
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.models import Group

from accounts.models import User
from catalog.models import Category, Product, ComplianceRecord
from orders.models import Order, PaymentProof
from store.models import PaymentMethod, FulfilmentMethod, PickupLocation, AuditLog

PASS = {"n": 0}
FAIL = {"n": 0}
def check(label, cond):
    if cond:
        PASS["n"] += 1
        print(f"  PASS  {label}")
    else:
        FAIL["n"] += 1
        print(f"  FAIL  {label}")

print("\n=== CUSTOMER JOURNEY ===")
c = Client()
r = c.get("/")
check("Homepage 200", r.status_code == 200)
check("Homepage shows Campus Connect brand", b"Campus Connect" in r.content)

r = c.get("/shop/")
check("Shop 200", r.status_code == 200)
check("Shop lists a demo product", b"Botanical Everyday Oil" in r.content)

r = c.get("/shop/?q=tote")
check("Search filters results", b"Textured Market Tote" in r.content and b"Botanical Everyday Oil" not in r.content)

oil = Product.objects.get(sku="CC-OIL-001")
r = c.get(f"/product/{oil.slug}/")
check("Product page 200", r.status_code == 200)
check("Product page shows price", b"18,500" in r.content or b"18500" in r.content)

r = c.post("/cart/add/", {"product_id": oil.id, "quantity": 2}, follow=True)
check("Add to cart ok", r.status_code == 200)
r = c.get("/cart/")
check("Cart shows item", b"Botanical Everyday Oil" in r.content)

tumbler = Product.objects.get(sku="CC-TUM-001")
r = c.post("/cart/add/", {"product_id": tumbler.id, "quantity": 99}, follow=True)
cart_qty = c.session.get("cart", {}).get(str(tumbler.id), 0)
check("Over-ordering blocked by stock", cart_qty <= tumbler.stock_quantity)

pm = PaymentMethod.objects.get(slug="airtel-money")
pickup_fm = FulfilmentMethod.objects.get(kind=FulfilmentMethod.PICKUP)
loc = PickupLocation.objects.filter(is_active=True).first()
r = c.get("/orders/checkout/")
check("Checkout page 200", r.status_code == 200)
r = c.post("/orders/checkout/", {
    "payment_method": pm.id, "fulfilment_method": pickup_fm.id,
    "pickup_location": loc.id, "contact_name": "Test Buyer",
    "contact_email": "buyer@example.com", "contact_phone": "+265999",
}, follow=True)
order = Order.objects.order_by("-id").first()
check("Order created with CC- number", order.number.startswith("CC-"))
check("Order status Payment Pending", order.status == Order.PAYMENT_PENDING)
check("Payment instructions shown", b"Airtel" in r.content or b"payment" in r.content.lower())

proof_file = SimpleUploadedFile("proof.png", b"\x89PNG\r\n\x1a\n" + b"0" * 50, content_type="image/png")
r = c.post(f"/orders/{order.number}/proof/", {"proof": proof_file, "reference": "TXN123"}, follow=True)
order.refresh_from_db()
check("Proof uploaded -> Payment Verification", order.status == Order.PAYMENT_VERIFICATION)
proof = PaymentProof.objects.filter(order=order).first()
check("Proof stored", proof is not None)
check("Proof not in public MEDIA path", "private_media" in proof.file.path)

r = c.get(f"/orders/{order.number}/track/")
check("Order tracking 200", r.status_code == 200)

print("\n=== PROOF ACCESS CONTROL ===")
anon = Client()
r = anon.get(f"/orders/proof/{proof.pk}/file/")
check("Proof not accessible to anonymous (403)", r.status_code == 403)

print("\n=== ADMIN JOURNEY ===")
admin = Client()
ok = admin.login(username="admin", password="Savana!Admin2026")
check("Admin login", ok)
r = admin.get("/backoffice/")
check("Backoffice dashboard 200", r.status_code == 200)
r = admin.get(f"/backoffice/orders/{order.number}/")
check("Admin order detail 200", r.status_code == 200)
r = admin.get(f"/orders/proof/{proof.pk}/file/")
check("Admin can access proof file", r.status_code == 200)

r = admin.post(f"/backoffice/orders/{order.number}/action/",
               {"action": "reject", "reason": "Amount did not match."}, follow=True)
order.refresh_from_db()
check("Reject payment -> Rejected", order.status == Order.REJECTED)
check("Rejection audit logged", AuditLog.objects.filter(action="payment_rejected").exists())

print("\n=== INVENTORY + CONFIRM FLOW ===")
c2 = Client()
c2.post("/cart/add/", {"product_id": oil.id, "quantity": 3}, follow=True)
c2.post("/orders/checkout/", {
    "payment_method": pm.id, "fulfilment_method": pickup_fm.id,
    "pickup_location": loc.id, "contact_name": "Buyer2",
    "contact_email": "b2@example.com", "contact_phone": "+265111",
}, follow=True)
order2 = Order.objects.order_by("-id").first()
pf = SimpleUploadedFile("p2.png", b"\x89PNG\r\n\x1a\n" + b"0" * 50, content_type="image/png")
c2.post(f"/orders/{order2.number}/proof/", {"proof": pf}, follow=True)
oil.refresh_from_db(); stock_before = oil.stock_quantity
admin.post(f"/backoffice/orders/{order2.number}/action/", {"action": "verify"}, follow=True)
order2.refresh_from_db(); oil.refresh_from_db()
check("Confirm payment -> Processing", order2.status == Order.PROCESSING)
check("Inventory decremented on confirm", oil.stock_quantity == stock_before - 3)
check("Stock committed flag set", order2.stock_committed)
admin.post(f"/backoffice/orders/{order2.number}/action/", {"action": "fulfil", "to_status": Order.READY}, follow=True)
admin.post(f"/backoffice/orders/{order2.number}/action/", {"action": "fulfil", "to_status": Order.FULFILLED}, follow=True)
order2.refresh_from_db()
check("Order fulfilled", order2.status == Order.FULFILLED)

print("\n=== INVENTORY ADJUST + STOREFRONT AVAILABILITY ===")
admin.post("/backoffice/inventory/adjust/", {"product_id": tumbler.id, "mode": "set", "amount": 0, "note": "sold out"}, follow=True)
tumbler.refresh_from_db()
check("Stock set to 0 flips status to Out of Stock", tumbler.status == Product.OUT_OF_STOCK)
admin.post("/backoffice/inventory/adjust/", {"product_id": tumbler.id, "mode": "increase", "amount": 4, "note": "restock"}, follow=True)
tumbler.refresh_from_db()
check("Restock flips back to Published", tumbler.status == Product.PUBLISHED and tumbler.stock_quantity == 4)

print("\n=== PRODUCT LIFECYCLE (admin -> storefront) ===")
cat = Category.objects.first()
newp = Product.objects.create(name="Test Widget", sku="CC-TEST-999", category=cat,
                              price=Decimal("5000"), stock_quantity=5, status=Product.DRAFT)
r = c.get(f"/product/{newp.slug}/")
check("Draft product NOT visible (404)", r.status_code == 404)
newp.status = Product.PUBLISHED; newp.save()
r = c.get(f"/product/{newp.slug}/")
check("Published product visible", r.status_code == 200)
newp.status = Product.UNPUBLISHED; newp.save()
r = c.get(f"/product/{newp.slug}/")
check("Unpublished product disappears (404)", r.status_code == 404)

print("\n=== REGULATED PRODUCT GATING ===")
reg = Product.objects.create(name="Regulated Item", sku="CC-REG-001", category=cat,
                             price=Decimal("9000"), stock_quantity=10,
                             status=Product.PUBLISHED,
                             regulatory_classification=Product.REGULATED)
check("Regulated product not transactable w/o approved compliance", not reg.is_transactable())
ComplianceRecord.objects.create(product=reg, status=ComplianceRecord.APPROVED)
reg.refresh_from_db()
check("Regulated product transactable after approval", reg.is_transactable())

print("\n=== RBAC (server-side) ===")
verifier = User.objects.create_user(username="verifier", password="Verifier!2026", is_staff=True)
verifier.groups.add(Group.objects.get(name="Payment Verifier"))
check("Payment Verifier has verify_payment", verifier.has_perm("orders.verify_payment"))
fulfiller = User.objects.create_user(username="fulfiller", password="Fulfil!2026", is_staff=True)
fulfiller.groups.add(Group.objects.get(name="Fulfilment Staff"))
check("Fulfilment Staff lacks verify_payment", not fulfiller.has_perm("orders.verify_payment"))

print("\n=== ERROR / EMPTY STATES / SEO ===")
r = c.get("/product/does-not-exist/")
check("Unknown product -> 404", r.status_code == 404)
r = Client().get("/cart/")
check("Empty cart renders 200", r.status_code == 200)
r = c.get("/sitemap.xml")
check("Sitemap 200", r.status_code == 200 and b"<urlset" in r.content)
r = c.get("/robots.txt")
check("Robots 200", r.status_code == 200 and b"Sitemap" in r.content)

print(f"\n==== RESULTS: {PASS['n']} passed, {FAIL['n']} failed ====")
