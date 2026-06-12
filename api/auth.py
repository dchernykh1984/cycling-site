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
