"""Entering races with one's own token (issue #438): what the registration page does, over the API.

A member enters themselves, the members whose registrations they manage (issue #315) and the people
without accounts they added -- one entry after another, as many as can be, each with its own answer,
as the page enters the people ticked on it -- lists their entries, changes an entry's own data and
cancels it while registration is open. The rules are the page's: registrations.registering builds,
checks and saves every entry, and the same forms say what is wrong.
"""

import datetime
from http import HTTPStatus
from typing import Literal

from django.db.models import Q
from django.shortcuts import get_object_or_404
from ninja import Field, Router, Schema, Status
from ninja.errors import HttpError

from accounts import managing, virtual_members
from accounts.models import VirtualMember
from api.auth import member_auth
from calendar_app.models import Competition, CompetitionInvite
from calendar_app.visibility import can_see, manages
from registrations import registering
from registrations.forms import EditRegistrationForm
from registrations.models import CompetitionRegistration
from registrations.views import can_self_edit

router = Router(tags=["registrations"])

_TEXT = 100
#: Whom an entry is for: the caller, a member they manage, a person without an account they added, or
#: -- where the event lets anyone be entered -- another person whose data the entry types in.
PERSON = r"^(me|other|member:\d+|virtual:\d+)$"


class EntryIn(Schema):
    person: str = Field("me", pattern=PERSON)
    # What the event's form takes; left out, it is filled in from the person, as the page fills it.
    # An event that takes only one's own data takes the names, gender and birth date from the person.
    first_name: str | None = Field(None, max_length=_TEXT)
    last_name: str | None = Field(None, max_length=_TEXT)
    gender: Literal["M", "F"] | None = None
    birth_date: datetime.date | None = None
    birth_year: int | None = None
    category_id: int | None = None
    team: str | None = Field(None, max_length=_TEXT)
    city: str | None = Field(None, max_length=_TEXT)
    additional_info: str | None = Field(None, max_length=_TEXT)


class EntriesIn(Schema):
    competition_id: int
    entries: list[EntryIn] = Field(max_length=virtual_members.BATCH_LIMIT)


class EntryResultOut(Schema):
    row: int  # the entry's place in the request, from 0
    registration_id: int | None  # none when it was not entered
    errors: dict[str, list[str]]  # why not, by field ("__all__" for the entry as a whole)


class EntryPatchIn(Schema):
    first_name: str | None = Field(None, max_length=_TEXT)
    last_name: str | None = Field(None, max_length=_TEXT)
    gender: Literal["M", "F"] | None = None
    birth_date: datetime.date | None = None
    team: str | None = Field(None, max_length=_TEXT)
    city: str | None = Field(None, max_length=_TEXT)
    additional_info: str | None = Field(None, max_length=_TEXT)


class EntryOut(Schema):
    id: int
    competition_id: int
    competition_title: str
    # "member:<id>" or "virtual:<id>", as an entry names them, or "me" for an entry under the caller's
    # own account -- theirs, or another person they typed in where anyone may be entered
    person: str
    first_name: str
    last_name: str
    gender: str
    birth_date: datetime.date
    category_id: int | None
    category: str
    team: str
    city: str
    additional_info: str
    is_approved: bool
    is_paid: bool
    is_rejected: bool
    registered_at: datetime.datetime
    can_change: bool  # whether the caller may still change or cancel it


def _mine(user, member_ids, added_ids) -> Q:
    """The caller's entries, their members' and the people's they added."""
    return Q(user=user) | Q(user_id__in=member_ids) | Q(virtual_member_id__in=added_ids)


def _scope(user):
    return managing.member_ids(user), virtual_members.ids(user)


def _entry_out(user, entry, member_ids, added_ids) -> EntryOut:
    if entry.virtual_member_id:
        person = f"virtual:{entry.virtual_member_id}"
    elif entry.user_id == user.pk:
        person = "me"
    else:
        person = f"member:{entry.user_id}"
    competition = entry.competition
    return EntryOut(
        id=entry.pk,
        competition_id=competition.pk,
        competition_title=competition.title,
        person=person,
        first_name=entry.first_name,
        last_name=entry.last_name,
        gender=entry.gender,
        birth_date=entry.birth_date,
        category_id=entry.category_id,
        category=entry.category.name if entry.category else "",
        team=entry.team.name if entry.team else "",
        city=entry.city,
        additional_info=entry.additional_info,
        is_approved=entry.is_approved,
        is_paid=entry.is_paid,
        is_rejected=entry.is_rejected,
        registered_at=entry.registered_at,
        can_change=manages(user, competition) or can_self_edit(user, competition, entry, member_ids, added_ids),
    )


def _person(user, competition, spec: str, member_ids):
    """``(person, refusal)``: whom the entry is for -- an account or a person without one, None for
    another person typed in -- or why the caller may not enter them."""
    if spec == "me":
        return user, ""
    if spec == "other":
        if registering.is_free(competition):
            return None, ""
        return None, "This event takes only one's own data: name the person, not 'other'"
    kind, _, pk = spec.partition(":")
    if kind == "member":
        if int(pk) in member_ids:
            return managing.members(user).get(member_id=int(pk)).member, ""
        return None, "Not a member whose registrations you manage"
    person = virtual_members.find(user, pk)
    return person, "" if person is not None else "Not a person you added"


def _form_data(competition, person, entry: EntryIn, typed: bool) -> dict:
    """The form as the page would send it: filled in from the person, then what the entry says --
    except, where the event takes only one's own data, the person's names, gender and birth date."""
    data: dict = {}
    if not typed:
        data = {
            "first_name": person.first_name,
            "last_name": person.last_name,
            "gender": person.gender,
            "city": person.city,
            "team_name": person.team,
        }
        if person.birth_date:
            data["birth_date"], data["birth_year"] = person.birth_date, person.birth_date.year
        if competition.show_additional_info_field and competition.additional_info_is_strava:
            data["additional_info"] = person.strava_link
    own_data_only = not registering.is_free(competition)
    given = {
        "first_name": entry.first_name,
        "last_name": entry.last_name,
        "gender": entry.gender,
        "birth_date": entry.birth_date,
        "birth_year": entry.birth_year or (entry.birth_date.year if entry.birth_date else None),
        "city": entry.city,
        "team_name": entry.team,
        "additional_info": entry.additional_info,
    }
    for field, value in given.items():
        if value is not None and not (own_data_only and field in registering.PROFILE_FIELDS):
            data[field] = value
    if entry.category_id is not None:
        data["category"] = entry.category_id
    elif not typed:
        offered = registering.available_categories(competition, person.gender, person.birth_date)
        if offered:
            data["category"] = offered[0].pk
    return data


def _open_competition(user, competition_id) -> Competition:
    """The event, as the registration page lets the caller enter it: one they see, approved or theirs
    to manage, with registration open and no relay team."""
    competition = get_object_or_404(Competition, pk=competition_id, is_deleted=False)
    if not can_see(user, competition) or (
        competition.status != Competition.Status.APPROVED and not manages(user, competition)
    ):
        raise HttpError(HTTPStatus.NOT_FOUND, "Not found")
    if not competition.is_registration_open():
        raise HttpError(HTTPStatus.CONFLICT, "Registration is not open")
    if competition.relay_enabled:
        raise HttpError(HTTPStatus.CONFLICT, "A relay team is entered on the event's page")
    return competition


@router.get("/", response=list[EntryOut], auth=member_auth, summary="My entries and those of the people I enter")
def my_entries(request, competition_id: int | None = None):
    user = request.auth
    member_ids, added_ids = _scope(user)
    entries = CompetitionRegistration.objects.filter(_mine(user, member_ids, added_ids), competition__is_deleted=False)
    if competition_id is not None:
        entries = entries.filter(competition_id=competition_id)
    entries = entries.select_related("competition", "competition__submitted_by", "category", "team").order_by(
        "-competition__date_start", "-registered_at"
    )
    return [_entry_out(user, entry, member_ids, added_ids) for entry in entries]


@router.post("/", response=list[EntryResultOut], auth=member_auth, summary="Enter people for a race, many at once")
def enter(request, payload: EntriesIn):
    """Each entry in turn, from the top, as many as can be: an entry refused says why and the next one
    is still tried, as the registration page does for the people ticked on it."""
    user = request.auth
    competition = _open_competition(user, payload.competition_id)
    member_ids = managing.member_ids(user)
    results = []
    for row, entry in enumerate(payload.entries):
        person, refusal = _person(user, competition, entry.person, member_ids)
        if refusal:
            results.append(EntryResultOut(row=row, registration_id=None, errors={"person": [refusal]}))
            continue
        typed = person is None
        account = user if typed else person
        if registering.cannot_fill(competition, account):
            refusal = "Their profile lacks a name, gender or date of birth"
            results.append(EntryResultOut(row=row, registration_id=None, errors={"person": [refusal]}))
            continue
        form = registering.bound_form(competition, account, _form_data(competition, account, entry, typed))
        registration = form.is_valid() and registering.register_one(competition, form, account, registered_by=user)
        if registration:
            if competition.invite_only and account != user and not isinstance(account, VirtualMember):
                CompetitionInvite.objects.get_or_create(competition=competition, user=account)
            results.append(EntryResultOut(row=row, registration_id=registration.pk, errors={}))
        else:
            errors = {
                field: [item["message"] for item in items] for field, items in form.errors.get_json_data().items()
            }
            results.append(EntryResultOut(row=row, registration_id=None, errors=errors))
    return results


def _own_entry(user, registration_id):
    member_ids, added_ids = _scope(user)
    entries = CompetitionRegistration.objects.filter(_mine(user, member_ids, added_ids), competition__is_deleted=False)
    return get_object_or_404(entries.select_related("competition"), pk=registration_id), member_ids, added_ids


@router.patch("/{registration_id}", response=EntryOut, auth=member_auth, summary="Change an entry's own data")
def change_entry(request, registration_id: int, payload: EntryPatchIn):
    """What the participant's own form changes, while registration is open: an event that takes only
    one's own data keeps the names, gender and birth date, and an approved entry goes back to review."""
    user = request.auth
    entry, member_ids, added_ids = _own_entry(user, registration_id)
    competition = entry.competition
    if not can_self_edit(user, competition, entry, member_ids, added_ids):
        raise HttpError(HTTPStatus.CONFLICT, "Registration is closed or the entry was rejected")
    current = {
        "first_name": entry.first_name,
        "last_name": entry.last_name,
        "birth_date": entry.birth_date,
        "gender": entry.gender,
        "city": entry.city,
        "team_name": entry.team.name if entry.team else "",
        "additional_info": entry.additional_info,
    }
    changes = payload.dict(exclude_unset=True)
    if "team" in changes:
        changes["team_name"] = changes.pop("team")
    current.update({field: value for field, value in changes.items() if value is not None})
    form = EditRegistrationForm(current, instance=entry, competition=competition, participant_fields_only=True)
    if not form.is_valid():
        raise HttpError(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "; ".join(f"{field}: {' '.join(str(m) for m in messages)}" for field, messages in form.errors.items()),
        )
    entry = registering.save_participant_change(form, competition, was_approved=entry.is_approved)
    return _entry_out(user, entry, member_ids, added_ids)


@router.delete(
    "/{registration_id}", response={HTTPStatus.NO_CONTENT: None}, auth=member_auth, summary="Cancel an entry"
)
def cancel_entry(request, registration_id: int):
    user = request.auth
    entry, member_ids, added_ids = _own_entry(user, registration_id)
    competition = entry.competition
    if not (manages(user, competition) or can_self_edit(user, competition, entry, member_ids, added_ids)):
        raise HttpError(HTTPStatus.CONFLICT, "Registration is closed or the entry was rejected")
    entry.delete()
    return Status(HTTPStatus.NO_CONTENT, None)
