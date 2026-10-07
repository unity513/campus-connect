"""Catalog: categories, products, images, inventory movements, compliance.

Products are never hard-coded in the frontend — the storefront reads only
published, transactable products from these tables.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils.text import slugify


class Category(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["sort_order", "name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:140]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Product(models.Model):
    DRAFT = "draft"
    PUBLISHED = "published"
    OUT_OF_STOCK = "out_of_stock"
    UNPUBLISHED = "unpublished"
    ARCHIVED = "archived"
    STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (PUBLISHED, "Published"),
        (OUT_OF_STOCK, "Out of Stock"),
        (UNPUBLISHED, "Unpublished"),
        (ARCHIVED, "Archived"),
    ]

    STANDARD = "standard"
    AGE_RESTRICTED = "age_restricted"
    REGULATED = "regulated"
    RESTRICTED = "restricted"
    REGULATORY_CHOICES = [
        (STANDARD, "Standard"),
        (AGE_RESTRICTED, "Age Restricted"),
        (REGULATED, "Regulated"),
        (RESTRICTED, "Restricted / Disabled"),
    ]

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    sku = models.CharField(max_length=64, unique=True)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="products"
    )
    short_description = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    sale_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    currency = models.CharField(max_length=8, default="MWK")

    stock_quantity = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=3)

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=DRAFT)
    is_featured = models.BooleanField(default=False)

    specifications = models.JSONField(default=dict, blank=True)
    extra_information = models.TextField(blank=True)
    warnings = models.TextField(blank=True)
    age_restriction = models.PositiveIntegerField(
        null=True, blank=True, help_text="Minimum age, if applicable."
    )
    regulatory_classification = models.CharField(
        max_length=20, choices=REGULATORY_CHOICES, default=STANDARD
    )
    compliance_information = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_featured", "name"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["category", "status"]),
            models.Index(fields=["slug"]),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:200] or self.sku.lower()
            slug, i = base, 1
            while Product.objects.exclude(pk=self.pk).filter(slug=slug).exists():
                i += 1
                slug = f"{base}-{i}"
            self.slug = slug
        super().save(*args, **kwargs)

    # --- Pricing ---------------------------------------------------------
    @property
    def effective_price(self):
        if self.sale_price is not None and self.sale_price < self.price:
            return self.sale_price
        return self.price

    @property
    def on_sale(self):
        return self.sale_price is not None and self.sale_price < self.price

    # --- Stock -----------------------------------------------------------
    @property
    def is_low_stock(self):
        return 0 < self.stock_quantity <= self.low_stock_threshold

    @property
    def in_stock(self):
        return self.stock_quantity > 0

    def availability_label(self):
        if not self.in_stock:
            return "Sold out"
        if self.is_low_stock:
            return f"Low stock — {self.stock_quantity} left"
        return "In stock"

    # --- Compliance gating ----------------------------------------------
    def requires_compliance(self):
        return self.regulatory_classification in (
            self.AGE_RESTRICTED, self.REGULATED, self.RESTRICTED
        )

    def compliance_ok(self):
        """Standard products are always ok. Regulated products need an
        approved ComplianceRecord before they can be sold or published."""
        if self.regulatory_classification == self.RESTRICTED:
            return False
        if not self.requires_compliance():
            return True
        rec = getattr(self, "compliance", None)
        return bool(rec and rec.status == ComplianceRecord.APPROVED)

    def is_transactable(self):
        """May a customer actually order this right now?"""
        return (
            self.status == self.PUBLISHED
            and self.in_stock
            and self.compliance_ok()
        )

    @property
    def primary_image(self):
        img = self.images.order_by("sort_order", "id").first()
        return img.image.url if img and img.image else (
            self.images.first().external_url if self.images.exists() else ""
        )

    def __str__(self):
        return f"{self.name} ({self.sku})"


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(upload_to="products/", blank=True, null=True)
    external_url = models.URLField(
        blank=True, help_text="Optional remote image URL (used if no file)."
    )
    alt_text = models.CharField(max_length=200, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    @property
    def display_url(self):
        if self.image:
            return self.image.url
        return self.external_url

    def __str__(self):
        return f"Image for {self.product.name}"


class InventoryMovement(models.Model):
    INCREASE = "increase"
    DECREASE = "decrease"
    CORRECTION = "correction"
    SALE = "sale"
    REASON_CHOICES = [
        (INCREASE, "Stock increase"),
        (DECREASE, "Stock reduction"),
        (CORRECTION, "Correction"),
        (SALE, "Order fulfilment"),
    ]

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="movements"
    )
    reason = models.CharField(max_length=16, choices=REASON_CHOICES)
    quantity_delta = models.IntegerField(help_text="Signed change applied.")
    resulting_quantity = models.PositiveIntegerField()
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="inventory_movements",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["product", "created_at"])]

    def __str__(self):
        return f"{self.product.sku} {self.quantity_delta:+d} -> {self.resulting_quantity}"


class ComplianceRecord(models.Model):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (APPROVED, "Approved"),
        (REJECTED, "Rejected"),
    ]

    product = models.OneToOneField(
        Product, on_delete=models.CASCADE, related_name="compliance"
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=PENDING)
    age_verification_required = models.BooleanField(default=False)
    required_declarations = models.JSONField(default=list, blank=True)
    merchant_license_info = models.TextField(blank=True)
    geographic_restrictions = models.CharField(max_length=255, blank=True)
    product_restrictions = models.TextField(blank=True)
    required_warnings = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="compliance_approvals",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Compliance[{self.get_status_display()}] for {self.product.sku}"
