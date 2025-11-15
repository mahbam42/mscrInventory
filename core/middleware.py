"""Custom middleware for enforcing global login requirements."""
from django.conf import settings
from django.contrib.auth.views import redirect_to_login


class LoginRequiredMiddleware:
    """Redirect anonymous users to the configured LOGIN_URL."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.exempt_paths = {
            self._normalize(value)
            for value in getattr(settings, "LOGIN_EXEMPT_PATHS", [])
        }
        self.exempt_prefixes = tuple(
            self._normalize(prefix)
            for prefix in getattr(settings, "LOGIN_EXEMPT_PREFIXES", ())
            if prefix
        )

    def __call__(self, request):
        if self._should_skip(request):
            return self.get_response(request)

        user = getattr(request, "user", None)
        if not (user and user.is_authenticated):
            return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)

        return self.get_response(request)

    def _should_skip(self, request) -> bool:
        path = self._normalize(request.path)
        if path in self.exempt_paths:
            return True
        for prefix in self.exempt_prefixes:
            if path.startswith(prefix):
                return True
        return False

    @staticmethod
    def _normalize(value: str) -> str:
        if not value:
            return ""
        return value if value.startswith("/") else f"/{value}"
