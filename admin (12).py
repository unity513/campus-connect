from django.contrib import admin
from django.utils import timezone

from store.services import audit

from .models import (
    Category, ComplianceRecord, InventoryMovement, Product, ProductImage,
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class ComplianceInline(admin.StackedInline):
    model = ComplianceRecord
    extra = 0
    can_delete = False


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "category", "price", "stock_quantity",
                    "status", "regulatory_classification", "is_featured",
                    "transactable")
    list_filter = ("status", "category", "regulatory_classification",
                   "is_featured")
    search_fields = ("name", "sku")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductImageInline, ComplianceInline]
    readonly_fields = ("created_at", "updated_at")
    actions = ["publish", "unpublish", "archive"]

    @admin.display(boolean=True, description="Sellable")
    def transactable(self, obj):
        return obj.is_transactable()

    def _can_publish(self, product):
        return product.compliance_ok()

    @admin.action(description="Publish selected products")
    def publish(self, request, queryset):
        published = blocked = 0
        for product in queryset:
            if not self._can_publish(product):
                blocked += 1
                continue
            product.status = Product.PUBLISHED
            product.save(update_fields=["status", "updated_at"])
            audit(request.user, "product_published", product, sku=product.sku)
            published += 1
        if published:
            self.message_user(request, f"Published {published} product(s).")
        if blocked:
            self.message_user(
                request,
                f"{blocked} product(s) blocked: regulated products need an "
                "approved compliance record first.",
                level="error",
            )

    @admin.action(description="Unpublish selected products")
    def unpublish(self, request, queryset):
        for product in queryset:
            product.status = Product.UNPUBLISHED
            product.save(update_fields=["status", "updated_at"])
            audit(request.user, "product_unpublished", product, sku=product.sku)
        self.message_user(request, "Selected products unpublished.")

    @admin.action(description="Archive selected products")
    def archive(self, request, queryset):
        queryset.update(status=Product.ARCHIVED, updated_at=timezone.now())
        self.message_user(request, "Selected products archived.")

    def save_model(self, request, obj, form, change):
        # Guard: regulated products cannot be saved as Published without an
        # approved compliance record (server-side enforcement).
        if obj.status == Product.PUBLISHED and not obj.compliance_ok():
            obj.status = Product.DRAFT
            self.message_user(
                request,
                "This product requires an approved compliance record before "
                "it can be published. Saved as Draft instead.",
                level="warning",
            )
        super().save_model(request, obj, form, change)
        audit(request.user, "product_created" if not change else "product_updated",
              obj, sku=obj.sku)


@admin.register(InventoryMovement)
class InventoryMovementAdmin(admin.ModelAdmin):
    list_display = ("product", "reason", "quantity_delta",
                    "resulting_quantity", "created_by", "created_at")
    list_filter = ("reason",)
    search_fields = ("product__name", "product__sku")
    readonly_fields = ("created_at",)


@admin.register(ComplianceRecord)
class ComplianceRecordAdmin(admin.ModelAdmin):
    list_display = ("product", "status", "age_verification_required",
                    "approved_by", "approved_at")
    list_filter = ("status", "age_verification_required")
    actions = ["approve", "reject"]

    @admin.action(description="Approve compliance")
    def approve(self, request, queryset):
        for rec in queryset:
            rec.status = ComplianceRecord.APPROVED
            rec.approved_by = request.user
            rec.approved_at = timezone.now()
            rec.save()
            audit(request.user, "compliance_approved", rec.product,
                  sku=rec.product.sku)
        self.message_user(request, "Compliance approved.")

    @admin.action(description="Reject compliance")
    def reject(self, request, queryset):
        queryset.update(status=ComplianceRecord.REJECTED)
        self.message_user(request, "Compliance rejected.")
