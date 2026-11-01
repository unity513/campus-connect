from django.contrib import admin

from .models import (
    Order, OrderItem, OrderStatusEvent, Payment, PaymentProof,
)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product_name", "sku", "unit_price", "quantity",
                       "line_total")
    can_delete = False


class StatusEventInline(admin.TabularInline):
    model = OrderStatusEvent
    extra = 0
    readonly_fields = ("from_status", "to_status", "note", "changed_by",
                       "created_at")
    can_delete = False


class PaymentInline(admin.StackedInline):
    model = Payment
    extra = 0
    readonly_fields = ("verified_by", "verified_at", "updated_at")


class ProofInline(admin.TabularInline):
    model = PaymentProof
    extra = 0
    readonly_fields = ("original_name", "content_type", "size_bytes",
                       "reference", "uploaded_by", "uploaded_at")
    fields = readonly_fields
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("number", "contact_name", "status", "total", "currency",
                    "payment_method", "created_at")
    list_filter = ("status", "payment_method", "fulfilment_method",
                   "created_at")
    search_fields = ("number", "contact_name", "contact_email",
                     "contact_phone")
    date_hierarchy = "created_at"
    readonly_fields = ("number", "subtotal", "delivery_fee", "total",
                       "created_at", "updated_at", "stock_committed")
    inlines = [OrderItemInline, PaymentInline, ProofInline, StatusEventInline]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("order", "method", "status", "amount", "verified_by",
                    "verified_at")
    list_filter = ("status", "method")
    search_fields = ("order__number", "reference")


@admin.register(PaymentProof)
class PaymentProofAdmin(admin.ModelAdmin):
    list_display = ("order", "original_name", "uploaded_by", "uploaded_at")
    search_fields = ("order__number", "reference")
    readonly_fields = ("uploaded_at",)
