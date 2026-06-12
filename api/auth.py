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


def is_admin(user) -> bool:
    from accounts.models import User

    return user.is_superuser or user.get_role_rank() >= user.ROLE_HIERARCHY.index(User.Role.ADMIN)
