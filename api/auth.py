from django.contrib.auth.models import AnonymousUser
from ninja.security import HttpBearer


class ApiTokenAuth(HttpBearer):
    """Authenticate requests using a user's personal API token (Bearer header)."""

    def authenticate(self, request, token):
        from django.core.exceptions import ValidationError

        from accounts.models import User
        from audit.middleware import _thread_locals

        try:
            user = User.objects.get(api_token=token)
        except (User.DoesNotExist, ValueError, ValidationError):
            return None
        request.user = user
        _thread_locals.user = user  # keep audit middleware in sync with Bearer auth
        return user


class OptionalApiTokenAuth(HttpBearer):
    """Like ApiTokenAuth but allows requests with no Authorization header.

    When no token is provided the request proceeds with an AnonymousUser so that
    public read endpoints are accessible without a token.  Providing a token that
    does not match any user still returns 401 (prevents accidental exposure from
    typos / stale tokens).
    """

    def __call__(self, request):
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            request.auth = AnonymousUser()
            return AnonymousUser()
        return super().__call__(request)

    def authenticate(self, request, token):
        from django.core.exceptions import ValidationError

        from accounts.models import User
        from audit.middleware import _thread_locals

        try:
            user = User.objects.get(api_token=token)
        except (User.DoesNotExist, ValueError, ValidationError):
            return None
        request.user = user
        _thread_locals.user = user
        return user


def is_admin(user) -> bool:
    from accounts.models import User

    if not hasattr(user, "get_role_rank"):
        return False
    return user.is_superuser or user.get_role_rank() >= user.ROLE_HIERARCHY.index(User.Role.ADMIN)
