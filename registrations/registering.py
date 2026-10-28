"""Entering one person for an event: what the registration page does for each person it enters.

The page enters the reader and, since issue #315, the members they manage, one form each; every
entry goes through ``register_one``, so one rule decides with what data a person is entered.
"""

import datetime
from typing import cast

from django import forms
from django.db import transaction
from django.utils.translation import gettext

from calendar_app.models import Competition

from .forms import RegistrationForm
from .models import CompetitionRegistration, RegistrationCategory, Team, check_duplicate

# Taken from the person's own profile, never from the form, unless the event lets anyone be entered
PROFILE_FIELDS = ("first_name", "last_name", "birth_date", "birth_year", "gender")


def is_free(competition) -> bool:
    """Whether the event lets anyone's data be typed in, not only the person's own profile."""
    return competition.registration_mode == "free"


def profile_incomplete(person) -> bool:
    """Whether ``person``'s profile lacks what an event taking only one's own data needs."""
    return not person.gender or not person.birth_date


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
    """The form as the page first shows it for ``person``: filled in from their profile."""
    categories = available_categories(competition, person.gender, person.birth_date)
    initial = {
        "first_name": person.first_name,
        "last_name": person.last_name,
        "gender": person.gender,
        "city": person.city,
        "team_name": person.team,
    }
    if competition.birth_date_mode == "year":
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
                birth_date = datetime.date(1900, 1, 1)
        else:
            birth_date = cleaned.get("birth_date") or (
                datetime.date(cleaned["birth_year"], 1, 1) if cleaned.get("birth_year") else datetime.date(1900, 1, 1)
            )

    with transaction.atomic():
        competition = Competition.objects.select_for_update().get(pk=competition.pk)
        if not relay_enabled and check_duplicate(competition, person, first_name, last_name, birth_date):
            form.add_error(None, gettext("You are already registered for this competition."))
            return None

        team_name = cleaned.get("team_name", "").strip()
        team = Team.get_or_restore(team_name) if team_name else None

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

        registration = CompetitionRegistration.objects.create(
            competition=competition,
            user=person,
            registered_by=registered_by,
            first_name=first_name,
            last_name=last_name,
            participant_names="<BR>".join(names),
            participant_birth_years="<BR>".join(birth_years),
            participant_cities="<BR>".join(cities),
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
