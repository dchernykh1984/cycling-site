"""E2E for the team and city suggestions on the registration page.

A suggestion is a name somebody typed when they registered, so it is shown as text: a team named
like a piece of markup must not become markup on the next person's page.
"""

import datetime

import pytest
from playwright.sync_api import Page, expect

from calendar_app.models import Competition
from registrations.models import Team
from tests.e2e.conftest import inject_session

_TEAM = '"><img src=x onerror="window.__xss=1">'


@pytest.mark.django_db(transaction=True)
def test_a_suggested_team_name_is_shown_as_text(page: Page, live_server, organizer):
    comp = Competition.objects.create(
        title_ru="Suggestions Race",
        date_start=datetime.date.today() + datetime.timedelta(days=30),
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
        registration_enabled=True,
        registration_mode=Competition.RegistrationMode.FREE,
        birth_date_mode=Competition.BirthDateMode.YEAR,
    )
    Team.objects.create(name=_TEAM)
    inject_session(page, live_server, organizer)
    page.goto(f"{live_server.url}/en/competitions/{comp.pk}/register/")

    page.locator(".js-team").first.press_sequentially("img")
    expect(page.locator("#team-datalist option")).to_have_count(1)

    assert page.locator("#team-datalist option").first.get_attribute("value") == _TEAM
    assert page.evaluate("window.__xss") is None
    assert page.locator("#team-datalist img").count() == 0
