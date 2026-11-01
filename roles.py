"""Role-based access control definitions for Campus Connect back office.

Permissions are enforced server-side (view-level checks + Django admin
permission system). The UI only hides what the server already forbids.
"""

SUPER_ADMIN = "Super Admin"
STORE_ADMIN = "Store Admin"
PAYMENT_VERIFIER = "Payment Verifier"
FULFILMENT_STAFF = "Fulfilment Staff"
CONTENT_MANAGER = "Content Manager"

# Each role maps to a set of app_label.codename permissions. Super Admin gets
# everything (handled as is_superuser or all perms).
ROLE_DEFINITIONS = {
    STORE_ADMIN: {
        "description": "Products, inventory, orders and customers.",
        "models": [
            "catalog.category", "catalog.product", "catalog.productimage",
            "catalog.inventorymovement", "catalog.compliancerecord",
            "orders.order", "orders.orderitem", "orders.payment",
            "orders.orderstatusevent", "accounts.customerprofile",
            "accounts.address",
        ],
        "perms": ["add", "change", "delete", "view"],
    },
    PAYMENT_VERIFIER: {
        "description": "Payment verification and payment-related order info.",
        "models": ["orders.order", "orders.payment", "orders.paymentproof"],
        "perms": ["view", "change"],
        "extra": ["orders.verify_payment", "orders.reject_payment"],
    },
    FULFILMENT_STAFF: {
        "description": "Only fulfilment / order-processing functions.",
        "models": ["orders.order"],
        "perms": ["view", "change"],
        "extra": ["orders.update_fulfilment"],
    },
    CONTENT_MANAGER: {
        "description": "Products and storefront content, no financial admin.",
        "models": [
            "catalog.category", "catalog.product", "catalog.productimage",
            "store.storesetting",
        ],
        "perms": ["add", "change", "delete", "view"],
    },
    SUPER_ADMIN: {
        "description": "Full access.",
        "models": [],
        "perms": [],
        "all": True,
    },
}


def sync_roles():
    """Create/refresh the role Groups and attach permissions. Idempotent."""
    from django.contrib.auth.models import Group, Permission
    from django.contrib.contenttypes.models import ContentType

    for role, spec in ROLE_DEFINITIONS.items():
        group, _ = Group.objects.get_or_create(name=role)
        if spec.get("all"):
            group.permissions.set(Permission.objects.all())
            continue
        perms = []
        for dotted in spec.get("models", []):
            app_label, model = dotted.split(".")
            try:
                ct = ContentType.objects.get(app_label=app_label, model=model)
            except ContentType.DoesNotExist:
                continue
            for action in spec.get("perms", []):
                codename = f"{action}_{model}"
                perms.extend(
                    Permission.objects.filter(content_type=ct, codename=codename)
                )
        for dotted in spec.get("extra", []):
            app_label, codename = dotted.split(".")
            perms.extend(Permission.objects.filter(codename=codename))
        group.permissions.set(perms)
