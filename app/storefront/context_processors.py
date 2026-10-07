"""Template globals available on every page (store identity, cart count)."""
from orders.services import Cart
from store.models import StoreSetting


def store_globals(request):
    cart = Cart(request)
    return {
        "STORE_NAME": StoreSetting.get("store.name", "Campus Connect"),
        "STORE_TAGLINE": StoreSetting.get(
            "store.tagline", "Simple products. Thoughtfully chosen."
        ),
        "STORE_CONTACT": StoreSetting.get("store.contact", {}),
        "cart_count": cart.count,
    }
