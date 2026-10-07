"""Customer registration, authentication and account dashboard."""
from django import forms
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect, render

from orders.models import Order

from .models import CustomerProfile, User


class RegisterForm(UserCreationForm):
    full_name = forms.CharField(max_length=160, required=True)
    email = forms.EmailField(required=True)
    phone = forms.CharField(max_length=32, required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "full_name", "email", "phone")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.phone = self.cleaned_data.get("phone", "")
        user.is_customer = True
        if commit:
            user.save()
            CustomerProfile.objects.create(
                user=user,
                full_name=self.cleaned_data["full_name"],
                phone=self.cleaned_data.get("phone", ""),
            )
        return user


def register(request):
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Welcome to Campus Connect. Your account is ready.")
            return redirect("accounts:dashboard")
    else:
        form = RegisterForm()
    return render(request, "accounts/register.html", {"form": form})


class SavanaLoginView(LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True


class SavanaLogoutView(LogoutView):
    pass


@login_required
def dashboard(request):
    orders = Order.objects.filter(customer=request.user).prefetch_related(
        "items", "proofs"
    )
    current = orders.exclude(
        status__in=[Order.FULFILLED, Order.CANCELLED, Order.REJECTED]
    )
    history = orders.filter(
        status__in=[Order.FULFILLED, Order.CANCELLED, Order.REJECTED]
    )
    profile, _ = CustomerProfile.objects.get_or_create(user=request.user)
    return render(request, "accounts/dashboard.html", {
        "current_orders": current,
        "order_history": history,
        "profile": profile,
        "addresses": request.user.addresses.all(),
    })


@login_required
def update_profile(request):
    profile, _ = CustomerProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        profile.full_name = request.POST.get("full_name", profile.full_name)
        profile.phone = request.POST.get("phone", profile.phone)
        profile.marketing_opt_in = bool(request.POST.get("marketing_opt_in"))
        profile.save()
        request.user.email = request.POST.get("email", request.user.email)
        request.user.phone = profile.phone
        request.user.save(update_fields=["email", "phone"])
        messages.success(request, "Your details have been updated.")
    return redirect("accounts:dashboard")
