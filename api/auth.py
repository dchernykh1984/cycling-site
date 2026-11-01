from http import HTTPStatus

from django.contrib.auth.models import AnonymousUser
from ninja.security import HttpBearer, SessionAuth


class ApiTokenAuth(HttpBearer):
    """Authenticate requests using a user's personal API token (Bearer header)."""

    def authenticate(self, request, token):
        from django.core.exceptions import ValidationError

        from accounts.models import User
        from audit.middleware import _thread_locals

        try:
            user = User.objects.get(api_token=token, is_active=True)
        except (User.DoesNotExist, ValueError, ValidationError):
            return None
        request.user = user
        _thread_locals.user = user  # keep audit middleware in sync with Bearer auth
        return user


class ConfirmedSessionAuth(SessionAuth):
    """The site's session, for a member who confirmed their address: an unconfirmed one may not use the API."""

    def authenticate(self, request, key):
        from accounts.access import needs_email_confirmation

        user = super().authenticate(request, key)
        return None if user is None or needs_email_confirmation(user) else user


# A confirmed member signed in on the site or holding a personal API token: what a member's own
# actions ask for, from the trainer page to managing other members' registrations.
member_auth = [ApiTokenAuth(), ConfirmedSessionAuth()]


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
            user = User.objects.get(api_token=token, is_active=True)
        except (User.DoesNotExist, ValueError, ValidationError):
            return None
        request.user = user
        _thread_locals.user = user
        return user


def competition_by_token(token: str):
    """The approved, not deleted event an upload token belongs to -- the token the timing tools send with a
    start list, finish times, live stats or a protocol -- or a 401 for any other token."""
    from django.core.exceptions import ValidationError
    from ninja.errors import HttpError

    from calendar_app.models import Competition

    try:
        return Competition.objects.get(upload_token=token, status=Competition.Status.APPROVED, is_deleted=False)
    except (Competition.DoesNotExist, ValidationError):
        raise HttpError(HTTPStatus.UNAUTHORIZED, "Invalid competition_token") from None
