"""E2E for rating an event one took part in (issue #436): the banner's way to the review and away once it
is answered."""

import datetime
import re

import pytest
from playwright.sync_api import Page, expect

from accounts.models import User
from calendar_app.models import Competition
from event_photos.models import IssuedBib
from protocols.models import Protocol
from ratings.models import Review
from registrations.models import CompetitionRegistration
from tests.e2e.conftest import inject_session

# The event has no place, so its days are counted in UTC: two days back, it is over everywhere
OVER = datetime.datetime.now(datetime.UTC).date() - datetime.timedelta(days=2)
BANNER = "Rate the events you took part in"


@pytest.fixture
def rider(db):
    return User.objects.create_user(
        username="rider",
        email="rider@test.local",
        password="testpass123!",
        role=User.Role.PARTICIPANT,
        first_name="Dana",
        last_name="Kim",
    )


def _took_part(organizer, rider):
    """An event that is over, the rider's entry in it with bib 7, and 7 in its protocol's data."""
    event = Competition.objects.create(
        title_ru="Autumn Cup",
        title_en="Autumn Cup",
        date_start=OVER,
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
    )
    entry = CompetitionRegistration.objects.create(
        competition=event,
        user=rider,
        first_name="Dana",
        last_name="Kim",
        birth_date=datetime.date(1990, 1, 1),
        gender="F",
    )
    IssuedBib.objects.create(competition=event, registration=entry, bib="7")
    columns = [{"id": "bib", "label": "Bib", "role": "bib"}]
    rows = [{"cells": {"bib": "7"}}]
    Protocol.objects.create(
        competition=event,
        protocol_type="absolute",
        document={"schema": 1, "sections": [{"type": "table", "columns": columns, "rows": rows}]},
    )
    return event


def _sign_in(page, live_server, user):
    page.context.clear_cookies()
    inject_session(page, live_server, user)


@pytest.mark.django_db(transaction=True)
def test_the_banner_leads_to_the_review_and_goes_once_it_is_sent(page: Page, live_server, organizer, rider):
    event = _took_part(organizer, rider)
    page.set_viewport_size({"width": 360, "height": 800})
    _sign_in(page, live_server, rider)
    page.goto(f"{live_server.url}/en/calendar/")
    banner = page.get_by_role("region", name=BANNER)
    expect(banner).to_contain_text("Autumn Cup")
    banner.get_by_role("link", name="Rate: Autumn Cup").click()
    expect(page).to_have_url(re.compile(rf"/en/ratings/events/{event.pk}/review/$"))
    page.locator('label[for="overall-4"]').click()
    expect(page.get_by_role("radio", name="4")).to_be_checked()
    page.get_by_label("What went well, and what could be better").fill("Clear course")
    page.get_by_role("button", name="Send the review").click()
    expect(page.get_by_text("Thank you! Nobody will know the review is yours.")).to_be_visible()
    expect(page.get_by_role("region", name=BANNER)).to_have_count(0)
    assert Review.objects.get().answers == {"overall": 4, "comment": "Clear course"}


@pytest.mark.django_db(transaction=True)
def test_refusing_from_the_banner_stays_on_the_page_and_the_banner_goes(page: Page, live_server, organizer, rider):
    _took_part(organizer, rider)
    _sign_in(page, live_server, rider)
    page.goto(f"{live_server.url}/en/knowledge/")
    page.get_by_role("region", name=BANNER).get_by_role("button", name="Do not rate: Autumn Cup").click()
    expect(page.get_by_text("We will not ask about this event again.")).to_be_visible()
    expect(page).to_have_url(re.compile(r"/en/knowledge/$"))
    expect(page.get_by_role("region", name=BANNER)).to_have_count(0)
    assert not Review.objects.exists()
