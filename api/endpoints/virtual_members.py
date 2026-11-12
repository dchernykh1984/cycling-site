"""People without accounts a member enters for starts (issue #438), as the profile's card keeps them.

Adding anyone takes the member's word, given once, that they may handle these people's personal data
(``POST /consent``). A batch is checked whole before anything is saved: a row with a mistake, or more
people than the member may add, saves nobody and says why, row by row. Somebody already added -- the
same names and date of birth -- is left as they are, so a batch sent twice adds nobody twice.

A person may be handed over (``accounts.transfers``) -- to the owner, into an account of their own, or to
another mentor, staying without an account: the member makes a link, the account asks through it, and the
member confirms -- the same rules as the profile's card.
"""

import datetime
import uuid
from http import HTTPStatus
from typing import Literal

from django.core.exceptions import ValidationError
from django.urls import reverse
from ninja import Field, Router, Schema, Status
from ninja.errors import HttpError

from accounts import roles, transfers, virtual_members
from accounts.models import VIRTUAL_NAME_LENGTH, VirtualMember, VirtualMemberTransfer
from api.auth import member_auth

router = Router(tags=["virtual members"])

_TEXT = 100
_ACHIEVEMENTS = VirtualMember._meta.get_field("sports_achievements").max_length


class VirtualMemberIn(Schema):
    last_name: str = Field(max_length=VIRTUAL_NAME_LENGTH)
    first_name: str = Field(max_length=VIRTUAL_NAME_LENGTH)
    gender: Literal["M", "F"]
    birth_date: datetime.date
    team: str = Field("", max_length=_TEXT)
    city: str = Field("", max_length=_TEXT)
    strava_link: str = Field("", max_length=_TEXT)  # a URL, as a profile's
    sports_achievements: str = Field("", max_length=_ACHIEVEMENTS)  # a rank or category, or the like


class VirtualMemberPatchIn(Schema):
    last_name: str | None = Field(None, max_length=VIRTUAL_NAME_LENGTH)
    first_name: str | None = Field(None, max_length=VIRTUAL_NAME_LENGTH)
    gender: Literal["M", "F"] | None = None
    birth_date: datetime.date | None = None
    team: str | None = Field(None, max_length=_TEXT)
    city: str | None = Field(None, max_length=_TEXT)
    strava_link: str | None = Field(None, max_length=_TEXT)
    sports_achievements: str | None = Field(None, max_length=_ACHIEVEMENTS)


class VirtualMembersIn(Schema):
    people: list[VirtualMemberIn] = Field(max_length=virtual_members.BATCH_LIMIT)
    dry_run: bool = False  # check the batch and say what it would do, saving nothing


class ClaimantOut(Schema):
    """The account that asked to take a person over: what tells it apart, and no more."""

    user_id: int
    name: str
    birth_year: int | None


class TransferOut(Schema):
    to: VirtualMemberTransfer.To  # the owner, into their own account, or a mentor, as a person without one
    url: str  # the link to send while it is live; empty once somebody asked through it, or it ran out
    expires_at: datetime.datetime
    claimed_by: ClaimantOut | None  # the account whose request waits for the member to confirm it
    keep_manager: bool  # that account -- the owner -- lets the member go on managing its registrations and photos


class VirtualMemberOut(Schema):
    id: int
    last_name: str
    first_name: str
    gender: str
    birth_date: datetime.date
    team: str
    city: str
    strava_link: str
    sports_achievements: str
    transfer: TransferOut | None = None  # the link handing the person over, or the request that came through it


class ClaimIn(Schema):
    key: uuid.UUID
    keep_manager: bool = False  # to the owner: let the person's manager go on managing my registrations and photos


class ClaimOut(Schema):
    person: str  # last and first name
    manager: str  # who confirms it
    to: VirtualMemberTransfer.To  # into my account, or into my list of people without an account


class VirtualMembersOut(Schema):
    consented: bool  # the member's word given; until then nobody can be added
    limit: int | None  # how many people the member may add in all; none for any number
    room: int | None  # how many more they may add now
    people: list[VirtualMemberOut]


class AddedOut(Schema):
    dry_run: bool
    created: list[VirtualMemberOut]  # with no id on a dry run
    existing: list[VirtualMemberOut]  # already added: the batch's rows that were left as they are


class RowError(Schema):
    row: int  # the row's place in the batch, from 0
    errors: dict[str, list[str]]


class BatchRefusalOut(Schema):
    detail: str
    rows: list[RowError]


def _transfer_out(request, link) -> TransferOut:
    claimant = link.claimed_by
    return TransferOut(
        to=link.to,
        url=request.build_absolute_uri(reverse("account_virtual_claim", kwargs={"key": link.key}))
        if link.is_live()
        else "",
        expires_at=link.expires_at,
        claimed_by=ClaimantOut(
            user_id=claimant.pk,
            name=claimant.public_display_name,
            birth_year=claimant.birth_date.year if claimant.birth_date else None,
        )
        if claimant is not None
        else None,
        keep_manager=link.keep_manager,
    )


def _out(person, transfer: TransferOut | None = None) -> VirtualMemberOut:
    return VirtualMemberOut(
        id=person.pk or 0,
        last_name=person.last_name,
        first_name=person.first_name,
        gender=person.gender,
        birth_date=person.birth_date,
        team=person.team,
        city=person.city,
        strava_link=person.strava_link,
        sports_achievements=person.sports_achievements,
        transfer=transfer,
    )


def _consented(user) -> None:
    if not virtual_members.consented(user):
        raise HttpError(
            HTTPStatus.FORBIDDEN,
            "Confirm first that you may handle these people's personal data: POST /api/v1/virtual-members/consent",
        )


def _typed(data: dict) -> dict:
    """What a request says of a person, without the spaces around its words, as the card's form keeps
    it: a registration takes the names as they stand."""
    return {field: value.strip() if isinstance(value, str) else value for field, value in data.items()}


def _checked(person: VirtualMember) -> dict[str, list[str]]:
    """What is wrong with ``person`` as the model holds it -- names, gender, a date of birth from 1900 to
    today -- by field; nothing when they may be saved."""
    try:
        person.full_clean(exclude=["owner"])
    except ValidationError as error:
        return {field: [str(message) for message in messages] for field, messages in error.message_dict.items()}
    return {}


def _person(user, virtual_member_id) -> VirtualMember:
    person = virtual_members.find(user, virtual_member_id)
    if person is None:
        raise HttpError(HTTPStatus.NOT_FOUND, "Not found")
    return person


@router.get("/", response=VirtualMembersOut, auth=member_auth, summary="The people without accounts I added")
def list_people(request):
    user = request.auth
    consented = virtual_members.consented(user)
    people = virtual_members.of(user) if consented else VirtualMember.objects.none()
    links = {link.person_id: link for link in transfers.links_of(user)} if consented else {}
    return VirtualMembersOut(
        consented=consented,
        limit=roles.virtual_members_limit(user),
        room=virtual_members.room(user),
        people=[
            _out(person, _transfer_out(request, links[person.pk]) if person.pk in links else None) for person in people
        ],
    )


@router.post("/consent", response={HTTPStatus.NO_CONTENT: None}, auth=member_auth, summary="I may handle their data")
def consent(request):
    """The member's word that they may handle the personal data of the people they add: they have the
    people's consent, or their legal representatives'. Given once; it is not taken back."""
    if roles.virtual_members_limit(request.auth) == 0:
        raise HttpError(HTTPStatus.FORBIDDEN, "Your role adds no people without accounts")
    virtual_members.consent(request.auth)
    return Status(HTTPStatus.NO_CONTENT, None)


@router.post(
    "/",
    response={HTTPStatus.OK: AddedOut, HTTPStatus.UNPROCESSABLE_ENTITY: BatchRefusalOut},
    auth=member_auth,
    summary="Add people without accounts, many at once",
)
def add_people(request, payload: VirtualMembersIn):
    """Add the batch whole or not at all: every row is checked first, and somebody already added is left
    as they are. ``dry_run`` checks and says what would be added, saving nothing."""
    user = request.auth
    _consented(user)
    known = {virtual_members.key(p.last_name, p.first_name, p.birth_date): p for p in virtual_members.of(user)}
    new, existing, refused = [], [], []
    for row, data in enumerate(payload.people):
        person = VirtualMember(owner=user, **_typed(data.dict()))
        errors = _checked(person)
        key = virtual_members.key(person.last_name, person.first_name, person.birth_date)
        if errors:
            refused.append(RowError(row=row, errors=errors))
        elif key in known:
            existing.append(known[key])
        else:
            known[key] = person
            new.append(person)
    if refused:
        return Status(
            HTTPStatus.UNPROCESSABLE_ENTITY, BatchRefusalOut(detail="Nobody is added: fix these rows", rows=refused)
        )
    room = virtual_members.room(user)
    if room is not None and len(new) > room:
        return Status(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            BatchRefusalOut(detail=f"Nobody is added: {len(new)} new, and you may add {room} more", rows=[]),
        )
    if not payload.dry_run:
        new = VirtualMember.objects.bulk_create(new)
    return AddedOut(dry_run=payload.dry_run, created=[_out(p) for p in new], existing=[_out(p) for p in existing])


@router.patch("/{virtual_member_id}", response=VirtualMemberOut, auth=member_auth, summary="Change a person I added")
def change_person(request, virtual_member_id: int, payload: VirtualMemberPatchIn):
    person = _person(request.auth, virtual_member_id)
    for field, value in _typed(payload.dict(exclude_unset=True)).items():
        if value is not None:
            setattr(person, field, value)
    errors = _checked(person)
    if errors:
        raise HttpError(HTTPStatus.UNPROCESSABLE_ENTITY, "; ".join(f"{k}: {' '.join(v)}" for k, v in errors.items()))
    if virtual_members.copy_of(request.auth, person.last_name, person.first_name, person.birth_date, but=person.pk):
        raise HttpError(HTTPStatus.CONFLICT, "You have already added this person")
    person.save()
    return _out(person)


@router.delete(
    "/{virtual_member_id}", response={HTTPStatus.NO_CONTENT: None}, auth=member_auth, summary="Delete a person I added"
)
def delete_person(request, virtual_member_id: int):
    """Their entries in races to come are cancelled; past races stay in the results."""
    _person(request.auth, virtual_member_id).delete()
    return Status(HTTPStatus.NO_CONTENT, None)


@router.post(
    "/transfers/claim",
    response={HTTPStatus.CREATED: ClaimOut},
    auth=member_auth,
    summary="Ask, through a link, to take over a person somebody added",
)
def claim(request, payload: ClaimIn):
    """To the owner: the person's entries and named bibs come to my account, and my profile's empty fields
    are filled from them. To a mentor: the person, with them, comes into my list of people without an
    account -- which takes my word about such people's data first (``POST /consent``), room for one more
    and no copy of them (409). Either once their manager confirms it; a link takes one request."""
    link = transfers.find(payload.key)
    if link is not None and link.to_mentor:
        _consented(request.auth)
    outcome = transfers.ask(request.auth, payload.key, payload.keep_manager)
    if outcome != transfers.ASKED or link is None:
        raise HttpError(
            HTTPStatus.NOT_FOUND if outcome == transfers.INVALID else HTTPStatus.CONFLICT,
            transfers.refusal(outcome, link),
        )
    return Status(
        HTTPStatus.CREATED,
        ClaimOut(
            person=str(link.person),
            manager=link.person.owner.public_display_name,
            to=VirtualMemberTransfer.To(link.to),
        ),
    )


@router.post(
    "/{virtual_member_id}/transfer",
    response={HTTPStatus.CREATED: TransferOut},
    auth=member_auth,
    summary="Make a link handing a person I added over: to the owner or to a mentor",
)
def issue_transfer(request, virtual_member_id: int, to: VirtualMemberTransfer.To = VirtualMemberTransfer.To.OWNER):
    """``to=owner`` (the default) hands the person into an account of their own, ``to=mentor`` to another
    member's list, still without an account. A new link replaces the old one, whatever it was for, and
    drops a request waiting; it lasts a week and takes one request. A member without a name in their
    profile is asked for one first (409)."""
    person = _person(request.auth, virtual_member_id)
    refusal = transfers.why_no_link(request.auth)
    if refusal:
        raise HttpError(HTTPStatus.CONFLICT, refusal)
    link = transfers.issue(person, to)
    return Status(HTTPStatus.CREATED, _transfer_out(request, link))


@router.delete(
    "/{virtual_member_id}/transfer",
    response={HTTPStatus.NO_CONTENT: None},
    auth=member_auth,
    summary="Take back a hand-over link nobody has asked through",
)
def cancel_transfer(request, virtual_member_id: int):
    """The link stops working, and the person may be handed over again, either way. A request already waiting
    is answered instead -- confirmed or rejected --, so there is nothing to take back then (404)."""
    if not transfers.cancel(request.auth, _person(request.auth, virtual_member_id).pk):
        raise HttpError(HTTPStatus.NOT_FOUND, "Nothing to take back: no link waits to be sent for this person")
    return Status(HTTPStatus.NO_CONTENT, None)


@router.post(
    "/{virtual_member_id}/transfer/confirm",
    response={HTTPStatus.NO_CONTENT: None},
    auth=member_auth,
    summary="Confirm the request: hand the person over",
)
def confirm_transfer(request, virtual_member_id: int):
    """To the owner, the person's entries and named bibs go to the account that asked; to a mentor, the
    person goes into that account's list with them -- unless it has filled up, or come to hold the
    person, since (409). Either way the person leaves my list."""
    try:
        done = transfers.confirm(request.auth, _person(request.auth, virtual_member_id).pk)
    except transfers.RefusedError as refused:
        raise HttpError(HTTPStatus.CONFLICT, str(refused)) from refused
    if done is None:
        raise HttpError(HTTPStatus.NOT_FOUND, "No request waits for this person")
    return Status(HTTPStatus.NO_CONTENT, None)


@router.post(
    "/{virtual_member_id}/transfer/reject",
    response={HTTPStatus.NO_CONTENT: None},
    auth=member_auth,
    summary="Reject the request; the link goes with it",
)
def reject_transfer(request, virtual_member_id: int):
    if not transfers.reject(request.auth, _person(request.auth, virtual_member_id).pk):
        raise HttpError(HTTPStatus.NOT_FOUND, "No request waits for this person")
    return Status(HTTPStatus.NO_CONTENT, None)
