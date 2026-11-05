"""People without accounts a member enters for starts (issue #438), as the profile's card keeps them.

Adding anyone takes the member's word, given once, that they may handle these people's personal data
(``POST /consent``). A batch is checked whole before anything is saved: a row with a mistake, or more
people than the member may add, saves nobody and says why, row by row. Somebody already added -- the
same names and date of birth -- is left as they are, so a batch sent twice adds nobody twice.
"""

import datetime
from http import HTTPStatus
from typing import Literal

from django.core.exceptions import ValidationError
from ninja import Field, Router, Schema, Status
from ninja.errors import HttpError

from accounts import roles, virtual_members
from accounts.models import VIRTUAL_NAME_LENGTH, VirtualMember
from api.auth import member_auth

router = Router(tags=["virtual members"])

_TEXT = 100


class VirtualMemberIn(Schema):
    last_name: str = Field(max_length=VIRTUAL_NAME_LENGTH)
    first_name: str = Field(max_length=VIRTUAL_NAME_LENGTH)
    gender: Literal["M", "F"]
    birth_date: datetime.date
    team: str = Field("", max_length=_TEXT)
    city: str = Field("", max_length=_TEXT)


class VirtualMemberPatchIn(Schema):
    last_name: str | None = Field(None, max_length=VIRTUAL_NAME_LENGTH)
    first_name: str | None = Field(None, max_length=VIRTUAL_NAME_LENGTH)
    gender: Literal["M", "F"] | None = None
    birth_date: datetime.date | None = None
    team: str | None = Field(None, max_length=_TEXT)
    city: str | None = Field(None, max_length=_TEXT)


class VirtualMembersIn(Schema):
    people: list[VirtualMemberIn] = Field(max_length=virtual_members.BATCH_LIMIT)
    dry_run: bool = False  # check the batch and say what it would do, saving nothing


class VirtualMemberOut(Schema):
    id: int
    last_name: str
    first_name: str
    gender: str
    birth_date: datetime.date
    team: str
    city: str


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


def _out(person) -> VirtualMemberOut:
    return VirtualMemberOut(
        id=person.pk or 0,
        last_name=person.last_name,
        first_name=person.first_name,
        gender=person.gender,
        birth_date=person.birth_date,
        team=person.team,
        city=person.city,
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
    return VirtualMembersOut(
        consented=consented,
        limit=roles.virtual_members_limit(user),
        room=virtual_members.room(user),
        people=[_out(person) for person in people],
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
