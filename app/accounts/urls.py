from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", views.SavanaLoginView.as_view(), name="login"),
    path("logout/", views.SavanaLogoutView.as_view(), name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("profile/", views.update_profile, name="update_profile"),
]
