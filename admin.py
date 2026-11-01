from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Address, CustomerProfile, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "is_staff", "is_customer",
                    "age_verified")
    list_filter = ("is_staff", "is_superuser", "is_customer", "groups")
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Campus Connect", {"fields": ("phone", "is_customer", "age_verified",
                               "date_of_birth")}),
    )


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ("full_name", "user", "phone", "marketing_opt_in",
                    "created_at")
    search_fields = ("full_name", "user__username", "user__email", "phone")


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("customer", "kind", "line1", "city", "is_default")
    list_filter = ("kind", "is_default")
    search_fields = ("customer__username", "line1", "city")
