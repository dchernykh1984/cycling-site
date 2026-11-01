"""Managing another member's registrations and photos (issue #315), as the profile's two sections do it.

The rules are the site's own, from accounts.managing: a member asks through a manager's link and
waits until the manager accepts; either side ends it; rights never pass along a chain. Each
operation reaches only the caller's own rows, so an id in the address can never touch anyone else's.
"""

import datetime
import uuid
from http import HTTPStatus

from django.urls import reverse
from ninja import Router, Schema, Status
from ninja.errors import HttpError

from accounts import managing
from api.auth import member_auth

router = Router(tags=["managing"])


class InviteOut(Schema):
    key: uuid.UUID
    url: str
    expires_at: datetime.datetime


class ManagerOut(Schema):
    user_id: int
    name: str
    waiting: bool  # the request still waits for this manager to accept it


class RequestOut(Schema):
    """A request waiting for the caller: what tells the member apart, and no more."""

    user_id: int
    last_name: str
    first_name: str
    team: str
    birth_year: int | None


class MemberOut(Schema):
    """A member the caller manages: the data a registration form takes, no email."""

    user_id: int
    last_name: str
    first_name: str
    birth_date: datetime.date | None
    gender: str
    city: str
    team: str


class ManagingOut(Schema):
    invite: InviteOut | None  # the live link; none when there is none or it ran out
    managers: list[ManagerOut]
    waiting: list[RequestOut]
    members: list[MemberOut]


class JoinIn(Schema):
    key: uuid.UUID


class CountOut(Schema):
    count: int


def _invite_out(request, invite) -> InviteOut:
    url = request.build_absolute_uri(reverse("account_managing_join", kwargs={"key": invite.key}))
    return InviteOut(key=invite.key, url=url, expires_at=invite.expires_at)


def _request_out(member) -> RequestOut:
    birth_year = member.birth_date.year if member.birth_date else None
    return RequestOut(
        user_id=member.pk,
        last_name=member.last_name,
        first_name=member.first_name,
        team=member.team,
        birth_year=birth_year,
    )


def _member_out(member) -> MemberOut:
    return MemberOut(
        user_id=member.pk,
        last_name=member.last_name,
        first_name=member.first_name,
        birth_date=member.birth_date,
        gender=member.gender,
        city=member.city,
        team=member.team,
    )


def _found(done) -> Status:
    if not done:
        raise HttpError(HTTPStatus.NOT_FOUND, "Not found")
    return Status(HTTPStatus.NO_CONTENT, None)


@router.get("/", response=ManagingOut, auth=member_auth, summary="My link, who manages me and whom I manage")
def overview(request):
    user = request.auth
    invite = managing.invite_of(user)
    return ManagingOut(
        invite=_invite_out(request, invite) if invite is not None and invite.is_valid() else None,
        managers=[
            ManagerOut(user_id=row.manager_id, name=row.manager.public_display_name, waiting=row.accepted_at is None)
            for row in managing.managers(user)
        ],
        waiting=[_request_out(row.member) for row in managing.waiting(user)],
        members=[_member_out(row.member) for row in managing.members(user)],
    )


@router.post(
    "/invite", response={HTTPStatus.CREATED: InviteOut}, auth=member_auth, summary="Make my link, or a new one"
)
def issue_invite(request):
    refusal = managing.why_no_link(request.auth)
    if refusal:
        raise HttpError(HTTPStatus.CONFLICT, refusal)
    return Status(HTTPStatus.CREATED, _invite_out(request, managing.issue_invite(request.auth)))


@router.delete("/invite", response={HTTPStatus.NO_CONTENT: None}, auth=member_auth, summary="Delete my link")
def delete_invite(request):
    managing.delete_invite(request.auth)
    return Status(HTTPStatus.NO_CONTENT, None)


@router.post(
    "/join", response={HTTPStatus.CREATED: ManagerOut}, auth=member_auth, summary="Ask, through a link, to be managed"
)
def join(request, payload: JoinIn):
    invite = managing.find_invite(payload.key)
    outcome = managing.ask(request.auth, payload.key)
    if outcome != managing.ASKED or invite is None:
        raise HttpError(
            HTTPStatus.NOT_FOUND if outcome == managing.INVALID else HTTPStatus.CONFLICT,
            managing.refusal(outcome, invite),
        )
    return Status(
        HTTPStatus.CREATED, ManagerOut(user_id=invite.manager_id, name=invite.manager.public_display_name, waiting=True)
    )


@router.post("/waiting/accept-all", response=CountOut, auth=member_auth, summary="Accept every request waiting")
def accept_all(request):
    return CountOut(count=managing.accept_all(request.auth))


@router.post("/waiting/reject-all", response=CountOut, auth=member_auth, summary="Reject every request waiting")
def reject_all(request):
    return CountOut(count=managing.reject_all(request.auth))


@router.post(
    "/waiting/{user_id}/accept", response={HTTPStatus.NO_CONTENT: None}, auth=member_auth, summary="Accept a request"
)
def accept(request, user_id: int):
    return _found(managing.accept(request.auth, user_id))


@router.post(
    "/waiting/{user_id}/reject", response={HTTPStatus.NO_CONTENT: None}, auth=member_auth, summary="Reject a request"
)
def reject(request, user_id: int):
    return _found(managing.reject(request.auth, user_id))


@router.delete(
    "/members/{user_id}", response={HTTPStatus.NO_CONTENT: None}, auth=member_auth, summary="Stop managing a member"
)
def drop(request, user_id: int):
    return _found(managing.drop(request.auth, user_id))


@router.delete(
    "/managers/{user_id}",
    response={HTTPStatus.NO_CONTENT: None},
    auth=member_auth,
    summary="Remove a manager, or withdraw my request",
)
def leave(request, user_id: int):
    return _found(managing.leave(request.auth, user_id))
