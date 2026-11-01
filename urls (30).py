from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("checkout/", views.checkout, name="checkout"),
    path("track/", views.track_lookup, name="track_lookup"),
    path("<str:number>/instructions/", views.instructions, name="instructions"),
    path("<str:number>/track/", views.track_order, name="track"),
    path("<str:number>/proof/", views.upload_proof, name="upload_proof"),
    path("proof/<int:pk>/file/", views.serve_proof, name="serve_proof"),
]
