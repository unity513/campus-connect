"""Customer-facing storefront views. All product data is read from the DB;
nothing is hard-coded."""
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from catalog.models import Category, Product
from catalog.services import InsufficientStock
from orders.services import Cart
from store.models import FulfilmentMethod
from store.services import track


def _published_products():
    return Product.objects.filter(
        status__in=[Product.PUBLISHED, Product.OUT_OF_STOCK]
    ).select_related("category").prefetch_related("images")


def home(request):
    products = _published_products()
    featured = products.filter(is_featured=True)[:8]
    if not featured:
        featured = products[:8]
    categories = Category.objects.filter(is_active=True)
    return render(request, "storefront/home.html", {
        "featured": featured,
        "categories": categories,
        "all_products": products[:12],
    })


def shop(request):
    products = _published_products()
    q = request.GET.get("q", "").strip()
    category_slug = request.GET.get("category", "").strip()
    sort = request.GET.get("sort", "featured")

    if q:
        products = products.filter(
            Q(name__icontains=q) | Q(short_description__icontains=q)
            | Q(description__icontains=q)
        )
    if category_slug:
        products = products.filter(category__slug=category_slug)

    sort_map = {
        "price_asc": "price",
        "price_desc": "-price",
        "name": "name",
        "newest": "-created_at",
        "featured": "-is_featured",
    }
    products = products.order_by(sort_map.get(sort, "-is_featured"), "name")

    paginator = Paginator(products, 12)
    page = paginator.get_page(request.GET.get("page"))

    return render(request, "storefront/shop.html", {
        "page_obj": page,
        "categories": Category.objects.filter(is_active=True),
        "q": q,
        "active_category": category_slug,
        "sort": sort,
        "total": paginator.count,
    })


def product_detail(request, slug):
    product = get_object_or_404(
        _published_products(), slug=slug
    )
    track("product_viewed", request, product_id=product.id, sku=product.sku)
    related = _published_products().filter(
        category=product.category
    ).exclude(pk=product.pk)[:4]
    return render(request, "storefront/product_detail.html", {
        "product": product,
        "related": related,
    })


@require_POST
def cart_add(request):
    product = get_object_or_404(Product, pk=request.POST.get("product_id"))
    try:
        qty = max(1, int(request.POST.get("quantity", 1)))
    except (TypeError, ValueError):
        qty = 1
    cart = Cart(request)
    try:
        cart.add(product, qty)
        track("product_added_to_cart", request, product_id=product.id, qty=qty)
        messages.success(request, f"Added {product.name} to your cart.")
    except InsufficientStock as exc:
        messages.error(request, str(exc))
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"count": cart.count})
    return redirect(request.POST.get("next") or "storefront:cart")


def cart_view(request):
    cart = Cart(request)
    return render(request, "storefront/cart.html", {
        "rows": cart.items(),
        "subtotal": cart.subtotal,
        "problems": cart.validate_stock(),
        "fulfilment_methods": FulfilmentMethod.objects.filter(is_active=True),
    })


@require_POST
def cart_update(request):
    cart = Cart(request)
    product = get_object_or_404(Product, pk=request.POST.get("product_id"))
    action = request.POST.get("action")
    try:
        if action == "remove":
            cart.remove(product)
        else:
            qty = int(request.POST.get("quantity", 1))
            cart.set_quantity(product, qty)
    except (ValueError, InsufficientStock) as exc:
        messages.error(request, str(exc))
    return redirect("storefront:cart")


def about(request):
    return render(request, "storefront/about.html")


def support(request):
    return render(request, "storefront/support.html")
