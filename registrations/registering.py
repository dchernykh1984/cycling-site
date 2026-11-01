"""Entering one person for an event: what the registration page does for each person it enters.

The page enters the reader and, since issue #315, the members they manage, one form each; every
entry goes through ``register_one``, so one rule decides with what data a person is entered.
"""

import datetime
from dataclasses import dataclass
from typing import cast

from django import forms
from django.db import transaction
from django.utils.translation import gettext

from accounts import managing
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


def available_categories(competition, gender, birth_date) -> list[RegistrationCategory]:
    """The open categories a person of this gender and birth date may enter; none without both."""
    if not (gender and birth_date):
        return []
    categories = RegistrationCategory.objects.filter(competition=competition, is_deleted=False)
    return [c for c in categories if c.matches(gender, birth_date) and c.is_open()]


def _form(competition, person, data=None, **kwargs) -> RegistrationForm:
    readonly = [] if is_free(competition) else list(PROFILE_FIELDS)
    return RegistrationForm(data, competition=competition, user=person, readonly_fields=readonly, **kwargs)


def _offer(form, categories) -> None:
    cast(forms.ModelChoiceField, form.fields["category"]).queryset = categories


def blank_form(competition, person, prefix=None) -> RegistrationForm:
    """The form as the page first shows it for ``person``: filled in from their profile; empty for
    nobody's, as for another person typed in where anyone may be entered."""
    if person is None:
        form = _form(competition, None, prefix=prefix)
        _offer(form, RegistrationCategory.objects.none())
        return form
    categories = available_categories(competition, person.gender, person.birth_date)
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
    if competition.show_additional_info_field and competition.additional_info_is_strava:
        initial["additional_info"] = person.strava_link
    form = _form(competition, person, initial=initial, prefix=prefix)
    _offer(form, RegistrationCategory.objects.filter(pk__in=[c.pk for c in categories]))
    return form


def bound_form(competition, person, data, prefix=None) -> RegistrationForm:
    """The form as submitted for ``person``: any of the event's categories, checked on entering."""
    form = _form(competition, person, data, prefix=prefix)
    _offer(form, RegistrationCategory.objects.filter(competition=competition, is_deleted=False))
    return form


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
        # For relay only check gender; birth years span multiple age groups
        cat_ok = not category or (
            category.is_open()
            and (category.matches_gender(gender) if relay_enabled else category.matches(gender, birth_date))
        )
        if not cat_ok:
            form.add_error("category", gettext("This category is not available."))
            return None

        if not competition.is_registration_open():
            form.add_error(None, gettext("Registration is no longer available."))
            return None

        # Only now, past every refusal: a refused entry must not create a team or bring one back.
        team_name = cleaned.get("team_name", "").strip()
        team = Team.get_or_restore(team_name) if team_name else None

        registration = CompetitionRegistration.objects.create(
            competition=competition,
            user=person,
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
            additional_info=cleaned.get("additional_info", ""),
            is_approved=not competition.require_approval,
            is_paid=not competition.require_payment,
        )

        Competition.objects.filter(pk=competition.pk, registration_mode_locked=False).update(
            registration_mode_locked=True
        )
    return registration


def already_entered(competition, person) -> bool:
    """Whether ``person`` holds an entry the event would refuse them a second of."""
    if not is_free(competition):
        return CompetitionRegistration.objects.filter(competition=competition, user=person).exists()
    if competition.allow_multiple_registrations or not person.birth_date:
        return False
    return check_duplicate(competition, person, person.first_name, person.last_name, person.birth_date)


@dataclass
class Row:
    """One person on the page for several (issue #315), and how entering them went."""

    key: str  # what the person's checkbox sends: their account's id, or "other"
    label: str
    form: RegistrationForm | None = None
    profile: object = None  # whose profile fills the form in: none for another person typed in
    blocked: str = ""  # why the person has no checkbox
    checked: bool = False
    entered: bool = False

    @property
    def prefix(self) -> str:
        return f"p{self.key}"

    @property
    def ids(self) -> str:
        """What starts the ids of the row's fields, so that two rows never share one."""
        return f"{self.prefix}-"


def rows_for(competition, user) -> list[Row] | None:
    """The people the page for several offers, top to bottom; None when it is the page for one.

    The reader first, then the members they manage by name, leaving out whoever is entered already
    unless the event takes several entries from one person; where anyone may be entered, one more
    for another person typed in. A person whose profile cannot fill an event that takes only one's
    own data is listed without a checkbox, with the reason.
    """
    if competition.relay_enabled:
        return None
    members = [row.member for row in managing.members(user)]
    if not members:
        return None
    rows = []
    for person in [user, *members]:
        if already_entered(competition, person):
            continue
        is_reader = person == user
        row = Row(
            key=str(person.pk),
            label=gettext("%(name)s (you)") % {"name": person.public_display_name}
            if is_reader
            else f"{person.last_name} {person.first_name}".strip() or person.public_display_name,
            profile=person,
        )
        if cannot_fill(competition, person):
            row.blocked = (
                gettext("Complete your profile to register: it lacks your name, gender or date of birth.")
                if is_reader
                else gettext("Their profile lacks a name, gender or date of birth: ask them to complete it.")
            )
        else:
            row.form = blank_form(competition, person, prefix=row.prefix)
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
            if competition.invite_only and account != user:
                CompetitionInvite.objects.get_or_create(competition=competition, user=account)
        else:
            everyone = False
    return everyone


def ticks_allowed(competition, user, data) -> bool:
    """Whether every box ticked in ``data`` is one the page may offer ``user``: themselves, a member
    they manage, or another person where anyone may be entered. Anything else is a forged request."""
    allowed = {str(user.pk), *(str(pk) for pk in managing.member_ids(user))}
    if is_free(competition):
        allowed.add("other")
    return set(data.getlist("person")) <= allowed
