"""Entering one person for an event: what the registration page does for each person it enters.

The page enters the reader and, since issue #315, the members they manage, one form each -- and,
since issue #438, the people without accounts they added; every entry goes through ``register_one``,
so one rule decides with what data a person is entered. A "person" here is an account or a person
without one: both carry what the form takes from a profile, under the same names.
"""

import datetime
from dataclasses import dataclass
from typing import cast

from django import forms
from django.db import transaction
from django.utils.translation import gettext

from accounts import managing, virtual_members
from accounts.models import VirtualMember
from calendar_app.models import Competition

from .forms import RegistrationForm
from .models import (
    RELAY_SEPARATOR,
    UNKNOWN_BIRTH_DATE,
    CompetitionRegistration,
    RegistrationCategory,
    Team,
    check_duplicate,
)

# Taken from the person's own profile, never from the form, unless the event lets anyone be entered
PROFILE_FIELDS = ("first_name", "last_name", "birth_date", "birth_year", "gender")


def is_free(competition) -> bool:
    """Whether the event lets anyone's data be typed in, not only the person's own profile."""
    return competition.registration_mode == competition.RegistrationMode.FREE


def profile_incomplete(person) -> bool:
    """Whether ``person``'s profile lacks what an event taking only one's own data needs."""
    return not person.gender or not person.birth_date


def cannot_fill(competition, person) -> bool:
    """Whether ``person``'s profile cannot fill an event that takes only one's own data: the form
    takes the names, the gender and the birth date from it, and nobody else may type them."""
    return not is_free(competition) and (
        profile_incomplete(person) or not (person.first_name.strip() and person.last_name.strip())
    )


def open_categories(competition) -> list[RegistrationCategory]:
    """The event's categories still taking entries."""
    return [c for c in RegistrationCategory.objects.filter(competition=competition, is_deleted=False) if c.is_open()]


def available_categories(competition, gender, birth_date, offered=None) -> list[RegistrationCategory]:
    """The open categories a person of this gender and birth date may enter; none without both.
    ``offered``, when given, are the event's open categories, asked once for a page of many people."""
    if not (gender and birth_date):
        return []
    return [
        c for c in (offered if offered is not None else open_categories(competition)) if c.matches(gender, birth_date)
    ]


def _form(competition, person, data=None, **kwargs) -> RegistrationForm:
    readonly = [] if is_free(competition) else list(PROFILE_FIELDS)
    return RegistrationForm(data, competition=competition, readonly_fields=readonly, **kwargs)


def _offer(form, categories) -> None:
    cast(forms.ModelChoiceField, form.fields["category"]).queryset = categories


def additional_info_from(competition, person) -> str | None:
    """What the event's additional field takes from ``person``'s account -- a member's, or a person's
    without one: their Strava link, or their date of birth in full (ISO, as a date field sends it);
    None where the field is the participant's own to type."""
    if not competition.show_additional_info_field:
        return None
    if competition.additional_info_is_strava:
        return person.strava_link
    if competition.additional_info_is_birth_date:
        return person.birth_date.isoformat() if person.birth_date else ""
    return None


def blank_form(competition, person, prefix=None, offered=None) -> RegistrationForm:
    """The form as the page first shows it for ``person``: filled in from their profile; empty for
    nobody's, as for another person typed in where anyone may be entered."""
    if person is None:
        form = _form(competition, None, prefix=prefix)
        _offer(form, RegistrationCategory.objects.none())
        return form
    categories = available_categories(competition, person.gender, person.birth_date, offered)
    initial = {
        "first_name": person.first_name,
        "last_name": person.last_name,
        "gender": person.gender,
        "city": person.city,
        "team_name": person.team,
    }
    if competition.birth_date_mode == competition.BirthDateMode.YEAR:
        initial["birth_year"] = person.birth_date.year if person.birth_date else None
    else:
        initial["birth_date"] = person.birth_date
    if categories:
        initial["category"] = categories[0].pk
    from_profile = additional_info_from(competition, person)
    if from_profile is not None:
        initial["additional_info"] = from_profile
    form = _form(competition, person, initial=initial, prefix=prefix)
    _offer(form, RegistrationCategory.objects.filter(pk__in=[c.pk for c in categories]))
    return form


def bound_form(competition, person, data, prefix=None) -> RegistrationForm:
    """The form as submitted for ``person``: any of the event's categories, checked on entering."""
    form = _form(competition, person, data, prefix=prefix)
    _offer(form, RegistrationCategory.objects.filter(competition=competition, is_deleted=False))
    return form


def _additional_info(competition, cleaned, person) -> str:
    """The entry's additional field: as the form sent it, but an event that takes only one's own data
    takes the date of birth from the person's account, whatever the form says."""
    if not is_free(competition) and competition.additional_info_is_birth_date and person is not None:
        return person.birth_date.isoformat() if person.birth_date else ""
    return cleaned.get("additional_info", "")


def _category_refusal(competition, form, category, gender, birth_date, relay_enabled) -> str:
    """Why the entry cannot go into ``category``; empty when it can.

    An event with categories puts every entry in one. The page for one asks it of the browser; a person
    folded away on the page for several (issue #439), or entered through the API, is held to the same
    here, and told when no category takes them at all. A relay is checked by gender alone: its birth
    years span several age groups.
    """
    if category is None:
        if not competition.registration_categories.filter(is_deleted=False).exists():
            return ""
        if relay_enabled or available_categories(competition, gender, birth_date):
            return str(form.fields["category"].error_messages["required"])
        return gettext("No open category of this event takes this gender and year of birth.")
    fits = category.matches_gender(gender) if relay_enabled else category.matches(gender, birth_date)
    return "" if category.is_open() and fits else gettext("This category is not available.")


def register_one(competition, form, person, registered_by, relay=None) -> CompetitionRegistration | None:
    """Enter ``person`` from the valid ``form``, submitted by ``registered_by``.

    Returns the registration, or None with the reason added to the form. An event that takes only
    the participant's own data takes it from ``person``'s profile, whatever the form says. ``relay``
    is a relay team's names, birth years and cities, already escaped.
    """
    cleaned = form.cleaned_data
    relay_enabled = relay is not None
    names, birth_years, cities = relay if relay is not None else ([], [], [])
    if not is_free(competition):
        first_name, last_name = person.first_name, person.last_name
        gender, birth_date = person.gender, person.birth_date
    else:
        first_name = "" if relay_enabled else cleaned["first_name"]
        last_name = "" if relay_enabled else cleaned["last_name"]
        gender = cleaned["gender"]
        if relay_enabled and birth_years:
            try:
                birth_date = datetime.date(int(birth_years[0]), 1, 1)
            except (ValueError, TypeError):
                birth_date = UNKNOWN_BIRTH_DATE
        else:
            birth_date = cleaned.get("birth_date") or (
                datetime.date(cleaned["birth_year"], 1, 1) if cleaned.get("birth_year") else UNKNOWN_BIRTH_DATE
            )

    with transaction.atomic():
        competition = Competition.objects.select_for_update().get(pk=competition.pk)
        if not relay_enabled and check_duplicate(competition, person, first_name, last_name, birth_date):
            # Where anyone may be entered a duplicate is a name and a birth year, whoever typed them
            if is_free(competition):
                said = gettext("A participant with this name and birth year is already registered.")
            elif person == registered_by:
                said = gettext("You are already registered for this competition.")
            else:
                said = gettext("Already registered for this competition.")
            form.add_error(None, said)
            return None

        category = cleaned.get("category")
        refusal = _category_refusal(competition, form, category, gender, birth_date, relay_enabled)
        if refusal:
            form.add_error("category", refusal)
            return None

        if not competition.is_registration_open():
            form.add_error(None, gettext("Registration is no longer available."))
            return None

        # Only now, past every refusal: a refused entry must not create a team or bring one back.
        team_name = cleaned.get("team_name", "").strip()
        team = Team.get_or_restore(team_name) if team_name else None

        registration = CompetitionRegistration.objects.create(
            competition=competition,
            **virtual_members.who(person),
            registered_by=registered_by,
            first_name=first_name,
            last_name=last_name,
            participant_names=RELAY_SEPARATOR.join(names),
            participant_birth_years=RELAY_SEPARATOR.join(birth_years),
            participant_cities=RELAY_SEPARATOR.join(cities),
            birth_date=birth_date,
            gender=gender,
            category=category,
            city="" if relay_enabled else cleaned.get("city", ""),
            team=team,
            additional_info=_additional_info(competition, cleaned, person),
            is_approved=not competition.require_approval,
            is_paid=not competition.require_payment,
        )

        lock_registration_mode(competition)
    return registration


def save_participant_change(form, competition, was_approved) -> CompetitionRegistration:
    """Save the entry a participant -- or whoever enters them -- changed through the participant's form:
    the team by its name, and an approved entry sent back to moderation when anything changed, so the
    organiser re-checks the data rather than it going through silently."""
    entry = form.save(commit=False)
    if "team_name" in form.fields:
        team_name = form.cleaned_data.get("team_name", "").strip()
        entry.team = Team.get_or_restore(team_name) if team_name else None
    if competition.require_approval and was_approved and form.has_changed():
        entry.is_approved = False
    entry.save()
    return entry


def lock_registration_mode(competition) -> None:
    """Fix who may be entered once somebody is in: the mode does not change under an entry."""
    Competition.objects.filter(pk=competition.pk, registration_mode_locked=False).update(registration_mode_locked=True)


def already_entered(competition, person) -> bool:
    """Whether ``person`` holds an entry the event would refuse them a second of."""
    if not is_free(competition):
        return CompetitionRegistration.objects.filter(competition=competition, **virtual_members.who(person)).exists()
    if competition.allow_multiple_registrations or not person.birth_date:
        return False
    return check_duplicate(competition, person, person.first_name, person.last_name, person.birth_date)


#: A page for this many people or more gets filters by name, team and category (issue #440): fewer
#: are read through at a glance.
FILTERED_FROM = 6


@dataclass
class Row:
    """One person on the page for several (issue #315), and how entering them went."""

    key: str  # what the person's checkbox sends: their account's id, "v" and a virtual member's id, or "other"
    label: str
    form: RegistrationForm | None = None
    profile: object = None  # whose profile fills the form in: none for another person typed in
    blocked: str = ""  # why the person has no checkbox
    checked: bool = False
    entered: bool = False
    virtual: bool = False  # a person without an account, added by the reader (issue #438)
    team: str = ""  # the person's team, for the page's filter (issue #440)
    fits: tuple[int, ...] = ()  # the open categories the person's gender and birth date fit, for the filter

    @property
    def prefix(self) -> str:
        return f"p{self.key}"

    @property
    def ids(self) -> str:
        """What starts the ids of the row's fields, so that two rows never share one."""
        return f"{self.prefix}-"


def rows_for(competition, user) -> list[Row] | None:
    """The people the page for several offers, top to bottom; None when it is the page for one.

    The reader first, then the members they manage by name and the people without accounts they added
    (issue #438), leaving out whoever is entered already unless the event takes several entries from
    one person; where anyone may be entered, one more for another person typed in. A person whose
    profile cannot fill an event that takes only one's own data is listed without a checkbox, with
    the reason.
    """
    if competition.relay_enabled:
        return None
    members = [row.member for row in managing.members(user)]
    added = list(virtual_members.of(user))
    if not members and not added:
        return None
    rows = []
    offered = open_categories(competition)
    # shortcut: two queries a person (whether they are entered, the categories their form offers):
    # 300 people take about 0.5 s, the hundred a section usually has a fifth of that; ask both for
    # everyone at once if members come to bring a thousand.
    for person in [user, *members, *added]:
        if already_entered(competition, person):
            continue
        is_reader = person == user
        virtual = isinstance(person, VirtualMember)
        row = Row(
            key=f"v{person.pk}" if virtual else str(person.pk),
            label=gettext("%(name)s (you)") % {"name": person.public_display_name}
            if is_reader
            else f"{person.last_name} {person.first_name}".strip() or person.public_display_name,
            profile=person,
            virtual=virtual,
        )
        row.team = person.team
        row.fits = tuple(c.pk for c in available_categories(competition, person.gender, person.birth_date, offered))
        if cannot_fill(competition, person):
            row.blocked = (
                gettext("Complete your profile to register: it lacks your name, gender or date of birth.")
                if is_reader
                else gettext("Their profile lacks a name, gender or date of birth: ask them to complete it.")
            )
        else:
            row.form = blank_form(competition, person, prefix=row.prefix, offered=offered)
        rows.append(row)
    if is_free(competition):
        rows.append(
            Row(key="other", label=gettext("Another person"), form=blank_form(competition, None, prefix="pother"))
        )
    return rows


def enter_rows(competition, rows, user, data) -> bool:
    """Enter the people ticked in ``data``, one by one from the top: as many as can be.

    Each row ticked gets its form as sent; a row entered is marked so, one refused keeps the reason
    in its form. A member's entry is theirs, submitted by ``user``; in an invite-only event the
    member is then let in as though they had opened its link. Returns whether everyone ticked was
    entered.
    """
    from calendar_app.models import CompetitionInvite

    chosen = set(data.getlist("person"))
    everyone = True
    for row in rows:
        if row.key not in chosen or row.blocked:
            continue
        row.checked = True
        account = row.profile or user
        row.form = bound_form(competition, account, data, prefix=row.prefix)
        if row.form.is_valid() and register_one(competition, row.form, account, registered_by=user):
            row.entered = True
            if competition.invite_only and account != user and not row.virtual:
                CompetitionInvite.objects.get_or_create(competition=competition, user=account)
        else:
            everyone = False
    return everyone


def ticks_allowed(competition, user, data) -> bool:
    """Whether every box ticked in ``data`` is one the page may offer ``user``: themselves, a member
    they manage, a person without an account they added, or another person where anyone may be
    entered. Anything else is a forged request."""
    allowed = {
        str(user.pk),
        *(str(pk) for pk in managing.member_ids(user)),
        *(f"v{pk}" for pk in virtual_members.ids(user)),
    }
    if is_free(competition):
        allowed.add("other")
    return set(data.getlist("person")) <= allowed
