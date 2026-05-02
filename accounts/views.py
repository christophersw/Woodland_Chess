from django.conf import settings
from django.contrib import auth, messages
from django.shortcuts import redirect, render

from .forms import LoginForm


def login_view(request):
    # If auth is disabled globally, skip straight to the dashboard.
    if not getattr(settings, "AUTH_ENABLED", True):
        return redirect(settings.LOGIN_REDIRECT_URL)

    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)

    form = LoginForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].strip().lower()
        password = form.cleaned_data["password"]
        user = auth.authenticate(request, username=email, password=password)
        if user is not None and user.is_active:
            auth.login(request, user)
            next_url = request.GET.get("next", "")
            if not next_url or not next_url.startswith("/"):
                next_url = settings.LOGIN_REDIRECT_URL
            return redirect(next_url)
        messages.error(request, "Invalid email or password.")

    return render(request, "accounts/login.html", {"form": form})


def logout_view(request):
    if request.method == "POST":
        auth.logout(request)
    return redirect(settings.LOGOUT_REDIRECT_URL)
