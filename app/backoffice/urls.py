from django.urls import path

from . import views

app_name = "backoffice"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("orders/", views.order_list, name="order_list"),
    path("orders/<str:number>/", views.order_detail, name="order_detail"),
    path("orders/<str:number>/action/", views.order_action, name="order_action"),
    path("inventory/", views.inventory, name="inventory"),
    path("inventory/adjust/", views.inventory_adjust, name="inventory_adjust"),
    path("audit/", views.audit_log, name="audit_log"),
]
