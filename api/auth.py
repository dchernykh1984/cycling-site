from ninja.security import HttpBearer


class ApiTokenAuth(HttpBearer):
    """Authenticate requests using a user's personal API token (Bearer header)."""

    def authenticate(self, request, token):
        from accounts.models import User

        try:
            user = User.objects.get(api_token=token)
        except User.DoesNotExist:
            return None
        request.user = user
        return user


def is_admin(user) -> bool:
    from accounts.models import User

    return user.is_superuser or user.get_role_rank() >= user.ROLE_HIERARCHY.index(User.Role.ADMIN)
