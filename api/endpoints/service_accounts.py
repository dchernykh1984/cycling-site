"""The accounts the site's own agents post through (issue #436), as the owners' profile card marks them.

What such an account posts is nobody's work to judge: its events carry no organizer's rating. The
accounts offered are those with an API token, and those marked already.
"""

from http import HTTPStatus

from ninja import Router, Schema, Status
from ninja.errors import HttpError

from accounts import roles, service_accounts
from api.auth import member_auth

router = Router(tags=["service accounts"])


class ServiceAccountOut(Schema):
    user_id: int
    name: str
    email: str
    service: bool  # marked as the account the site's agents post through


def _owner(user) -> None:
    if not roles.at_least(user, roles.MARK_SERVICE_ACCOUNTS):
        raise HttpError(HTTPStatus.FORBIDDEN, "Only the owners mark the service accounts")


@router.get(
    "/", response=list[ServiceAccountOut], auth=member_auth, summary="The accounts to mark, and which are (owners)"
)
def list_accounts(request):
    _owner(request.auth)
    return [
        ServiceAccountOut(
            user_id=user.pk, name=user.public_display_name, email=user.email, service=user.is_service_account
        )
        for user in service_accounts.candidates()
    ]


@router.put(
    "/{user_id}", response={HTTPStatus.NO_CONTENT: None}, auth=member_auth, summary="Mark a service account (owners)"
)
def mark(request, user_id: int):
    _owner(request.auth)
    if not service_accounts.set_marked(user_id, True):
        raise HttpError(HTTPStatus.NOT_FOUND, "Not an account with an API token")
    return Status(HTTPStatus.NO_CONTENT, None)


@router.delete(
    "/{user_id}", response={HTTPStatus.NO_CONTENT: None}, auth=member_auth, summary="Take the mark back (owners)"
)
def unmark(request, user_id: int):
    _owner(request.auth)
    if not service_accounts.set_marked(user_id, False):
        raise HttpError(HTTPStatus.NOT_FOUND, "Not an account with an API token")
    return Status(HTTPStatus.NO_CONTENT, None)
