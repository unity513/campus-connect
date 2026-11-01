from django.urls import path

from . import views

app_name = "storefront"

urlpatterns = [
    path("", views.home, name="home"),
    path("shop/", views.shop, name="shop"),
    path("product/<slug:slug>/", views.product_detail, name="product"),
    path("cart/", views.cart_view, name="cart"),
    path("cart/add/", views.cart_add, name="cart_add"),
    path("cart/update/", views.cart_update, name="cart_update"),
    path("about/", views.about, name="about"),
    path("support/", views.support, name="support"),
]
