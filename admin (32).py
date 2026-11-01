from django.contrib import admin

from .models import (
    AnalyticsEvent, AuditLog, FulfilmentMethod, MerchantProfile, Notification,
    NotificationTemplate, PaymentMethod, PickupLocation, StoreSetting,
)


@admin.register(StoreSetting)
class StoreSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "group", "label")
    list_filter = ("group",)
    search_fields = ("key", "label")


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "requires_proof",
                    "sort_order")
    list_editable = ("is_active", "sort_order")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(PickupLocation)
class PickupLocationAdmin(admin.ModelAdmin):
    list_display = ("name", "address", "is_active")
    list_editable = ("is_active",)


@admin.register(FulfilmentMethod)
class FulfilmentMethodAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "fee", "is_active", "sort_order")
    list_editable = ("fee", "is_active", "sort_order")
    list_filter = ("kind", "is_active")


@admin.register(MerchantProfile)
class MerchantProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "contact_name", "contact_email", "is_active")
    filter_horizontal = ("supported_categories", "payment_methods",
                         "fulfilment_methods", "pickup_locations")


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ("event", "subject", "is_active")
    list_editable = ("is_active",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("event", "recipient", "order_number", "is_read",
                    "provider", "created_at")
    list_filter = ("event", "is_read", "provider")
    search_fields = ("order_number", "subject")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "user", "object_type", "object_id",
                    "created_at")
    list_filter = ("action", "object_type")
    search_fields = ("action", "object_id")
    readonly_fields = ("user", "action", "object_type", "object_id",
                       "metadata", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AnalyticsEvent)
class AnalyticsEventAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at", "session_key")
    list_filter = ("name",)
    readonly_fields = ("name", "properties", "session_key", "created_at")
