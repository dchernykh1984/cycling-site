from ninja.security import HttpBearer

_ANONYMOUS = object()  # sentinel for unauthenticated requests in optional auth


class OptionalApiTokenAuth(HttpBearer):
    """Like ApiTokenAuth but never raises 401 - passes anonymous requests through as _ANONYMOUS."""

    def __call__(self, request):
        result = super().__call__(request)
        return _ANONYMOUS if result is None else result

    def authenticate(self, request, token):
        from accounts.models import User
        from audit.middleware import _thread_locals

        try:
            user = User.objects.get(api_token=token)
        except User.DoesNotExist:
            return _ANONYMOUS
        request.user = user
        _thread_locals.user = user
        return user


class ApiTokenAuth(HttpBearer):
    """Authenticate requests using a user's personal API token (Bearer header)."""

    def authenticate(self, request, token):
        from accounts.models import User
        from audit.middleware import _thread_locals

        try:
            user = User.objects.get(api_token=token)
        except User.DoesNotExist:
            return None
        request.user = user
        _thread_locals.user = user  # keep audit middleware in sync with Bearer auth
        return user


def is_admin(user) -> bool:
    from accounts.models import User

    return user.is_superuser or user.get_role_rank() >= user.ROLE_HIERARCHY.index(User.Role.ADMIN)
