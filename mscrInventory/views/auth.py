"""Authentication helper views."""
from django.conf import settings
from django.contrib.auth import logout
from django.shortcuts import redirect


def logout_view(request):
    """Log the user out and redirect to the configured page."""
    logout(request)
    return redirect(settings.LOGOUT_REDIRECT_URL)
