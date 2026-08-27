"""E2E for the registration category dropdown filtering by birth year.

A "2020-2025" year category must include the boundary years 2020 and 2025. The client-side filter
compared a locally-built birth date against a UTC-parsed bound, so in a timezone ahead of UTC the
lower boundary year was wrongly dropped -- this test runs the browser in Asia/Almaty (UTC+5/+6) to
reproduce that, and would fail against the old strict/UTC comparison.
"""

import datetime

import pytest
from playwright.sync_api import Page, expect

from calendar_app.models import Competition
from registrations.models import RegistrationCategory
from tests.e2e.conftest import inject_session

_CATEGORY_NAME = "Girls 2020-2025"


@pytest.fixture
def browser_context_args(browser_context_args):
    # The boundary-year bug only manifests when the browser is ahead of UTC.
    return {**browser_context_args, "timezone_id": "Asia/Almaty"}


@pytest.fixture
def year_competition(db, organizer):
    comp = Competition.objects.create(
        title_ru="Reg Boundary Race",
        date_start=datetime.date(2030, 9, 1),
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
        registration_enabled=True,
        registration_mode=Competition.RegistrationMode.FREE,
        birth_date_mode=Competition.BirthDateMode.YEAR,
    )
    RegistrationCategory.objects.create(
        competition=comp,
        name=_CATEGORY_NAME,
        male=False,
        female=True,
        birth_from=datetime.date(2020, 1, 1),
        birth_to=datetime.date(2025, 12, 31),
    )
    return comp


def _category_option(page: Page):
    return page.locator("#category-select option", has_text=_CATEGORY_NAME)


@pytest.mark.django_db(transaction=True)
def test_birth_year_boundaries_keep_category(page: Page, live_server, organizer, year_competition):
    inject_session(page, live_server, organizer)
    page.goto(f"{live_server.url}/ru/competitions/{year_competition.pk}/register/")
    page.check("#gender_f")
    birth_year = page.locator('input[name="birth_year"]')

    # Lower boundary (the reported failing case) and upper boundary are both inclusive.
    birth_year.fill("2020")
    expect(_category_option(page)).to_have_count(1)

    birth_year.fill("2025")
    expect(_category_option(page)).to_have_count(1)

    birth_year.fill("2023")
    expect(_category_option(page)).to_have_count(1)

    # Just outside the range stays excluded.
    birth_year.fill("2019")
    expect(_category_option(page)).to_have_count(0)

    birth_year.fill("2026")
    expect(_category_option(page)).to_have_count(0)
