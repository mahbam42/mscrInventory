"""Authentication helper views."""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout, views as auth_views
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import Group
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from mscrInventory.forms import PublicUserCreateForm


class LoginView(auth_views.LoginView):
    """Custom login view that surfaces the public signup modal."""
    template_name = "registration/login.html"

    def get_context_data(self, **kwargs):
        """Inject the signup form to support modal toggling."""
        context = super().get_context_data(**kwargs)
        context.setdefault("signup_form", PublicUserCreateForm(prefix="signup"))
        context.setdefault("show_signup_modal", False)
        return context


@require_POST
def signup_view(request):
    """Handle self-service account creation for pending users."""

    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)

    signup_form = PublicUserCreateForm(request.POST, prefix="signup")
    login_form = AuthenticationForm(request=request)

    if signup_form.is_valid():
        new_user = signup_form.save()
        pending_group, _ = Group.objects.get_or_create(name="pending")
        new_user.groups.add(pending_group)
        messages.success(
            request,
            "Account requested. You will be able to sign in after an administrator approves access.",
        )
        return redirect(reverse("login"))

    context = {
        "form": login_form,
        "signup_form": signup_form,
        "show_signup_modal": True,
    }
    return render(request, "registration/login.html", context)


def logout_view(request):
    """Log the user out and redirect to the configured page."""

    logout(request)
    return redirect(settings.LOGOUT_REDIRECT_URL)
