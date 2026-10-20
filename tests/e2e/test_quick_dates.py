"""Quick date ranges above the calendar, list and map (issue #330).

"When can I ride this weekend" is the question people bring from the chats; it should not take two
date fields to ask.
"""

import datetime
import re

import pytest
from playwright.sync_api import Page, expect

from calendar_app.models import Competition

TODAY = datetime.date.today()


def _weekend(today=TODAY):
    """This weekend while it lasts (Sunday still has today), else the next one."""
    if today.weekday() == 6:
        return today, today
    saturday = today + datetime.timedelta(days=5 - today.weekday())
    return saturday, saturday + datetime.timedelta(days=1)


@pytest.fixture
def weekend_ride(db, organizer):
    return Competition.objects.create(
        title_ru="Weekend ride",
        date_start=_weekend()[0],
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
    )


@pytest.mark.django_db(transaction=True)
def test_weekend_shows_the_weekend_as_a_list(page: Page, live_server, weekend_ride):
    page.goto(f"{live_server.url}/ru/calendar/")
    page.locator('[data-quick-dates="weekend"]').click()
    expect(page.locator(".fc-listWeekend-view")).to_be_visible()
    expect(page.locator(".fc-list-event:visible", has_text="Weekend ride")).to_have_count(1)
    expect(page.locator('[data-quick-dates="weekend"].active')).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_the_arrow_moves_to_the_next_weekend(page: Page, live_server):
    page.goto(f"{live_server.url}/ru/calendar/")
    page.locator('[data-quick-dates="weekend"]').click()
    expect(page.locator(".fc-listWeekend-view")).to_be_visible()
    following = _weekend()[0] + datetime.timedelta(days=7)
    page.locator(".fc-next-button").click()
    expect(page.locator(".fc-toolbar-title")).to_contain_text(f"{following.day}")
    # Paging away from this weekend: the button no longer claims it.
    expect(page.locator('[data-quick-dates="weekend"].active')).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_season_is_the_calendar_year(page: Page, live_server):
    page.goto(f"{live_server.url}/ru/calendar/")
    page.locator('[data-quick-dates="season"]').click()
    expect(page.locator(".fc-listSeason-view")).to_be_visible()
    expect(page.locator(".fc-toolbar-title")).to_have_text(str(TODAY.year))


@pytest.mark.django_db(transaction=True)
def test_month_goes_back_to_the_month_view(page: Page, live_server):
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{live_server.url}/ru/calendar/")
    page.locator('[data-quick-dates="season"]').click()
    expect(page.locator(".fc-listSeason-view")).to_be_visible()
    page.locator('[data-quick-dates="month"]').click()
    expect(page.locator(".fc-dayGridMonth-view")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_the_list_fills_its_date_fields(page: Page, live_server):
    page.goto(f"{live_server.url}/ru/calendar/list/")
    page.locator('[data-quick-dates="weekend"]').click()
    saturday, sunday = _weekend()
    expect(page).to_have_url(re.compile(f"date_from={saturday:%Y-%m-%d}.*date_to={sunday:%Y-%m-%d}"))
    expect(page.locator('[data-quick-dates="weekend"].active')).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_the_lists_default_range_lights_month(page: Page, live_server):
    """The list opens on the thirty days ahead, which is exactly what Month means."""
    page.goto(f"{live_server.url}/ru/calendar/list/?reset=1")
    expect(page.locator('[data-quick-dates="month"].active')).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_the_map_fills_its_date_fields(page: Page, live_server):
    page.goto(f"{live_server.url}/ru/calendar/map/")
    page.locator('[data-quick-dates="season"]').click()
    expect(page.locator("#map-date-from")).to_have_value(f"{TODAY.year}-01-01")
    expect(page.locator("#map-date-to")).to_have_value(f"{TODAY.year}-12-31")


@pytest.mark.django_db(transaction=True)
def test_a_range_picked_on_the_calendar_travels_to_the_list(page: Page, live_server):
    page.goto(f"{live_server.url}/ru/calendar/")
    page.locator('[data-quick-dates="weekend"]').click()
    expect(page.locator(".fc-listWeekend-view")).to_be_visible()
    page.locator("#view-link-list").click()
    saturday, sunday = _weekend()
    expect(page.locator('input[name="date_from"]')).to_have_value(f"{saturday:%Y-%m-%d}")
    expect(page.locator('input[name="date_to"]')).to_have_value(f"{sunday:%Y-%m-%d}")
