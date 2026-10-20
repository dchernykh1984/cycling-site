"""The calendar's arrows, Today and month picker on the list and the map too (issue #330)."""

import calendar
import datetime
import re

import pytest
from django.utils import timezone
from playwright.sync_api import Page, expect


def _today() -> datetime.date:
    # The list and the map count from the site's day (Asia/Almaty), whatever the browser's is.
    return timezone.localdate()


def _month_after(day: datetime.date) -> tuple[datetime.date, datetime.date]:
    first = (day.replace(day=1) + datetime.timedelta(days=32)).replace(day=1)
    return first, first.replace(day=calendar.monthrange(first.year, first.month)[1])


def _this_weekend(today: datetime.date) -> datetime.date:
    """The Saturday of the weekend the quick button picks (a Sunday stands for its own)."""
    if today.weekday() == 6:
        return today - datetime.timedelta(days=1)
    return today + datetime.timedelta(days=5 - today.weekday())


@pytest.mark.django_db(transaction=True)
def test_the_list_steps_to_the_next_calendar_month(page: Page, live_server):
    page.goto(f"{live_server.url}/ru/calendar/list/?reset=1")
    page.locator('#date-nav [data-date-nav="1"]').click()
    first, last = _month_after(_today())
    expect(page).to_have_url(re.compile(f"date_from={first:%Y-%m-%d}&date_to={last:%Y-%m-%d}"))
    expect(page.locator("#date-nav-month")).to_have_value(str(first.month))
    expect(page.locator("#date-nav-year")).to_have_value(str(first.year))


@pytest.mark.django_db(transaction=True)
def test_the_list_jumps_to_a_picked_month(page: Page, live_server):
    page.goto(f"{live_server.url}/ru/calendar/list/?reset=1")
    year = _today().year
    page.locator("#date-nav-month").select_option("1")
    expect(page).to_have_url(re.compile(f"date_from={year}-01-01&date_to={year}-01-31"))


@pytest.mark.django_db(transaction=True)
def test_the_map_pages_a_weekend_by_weeks(page: Page, live_server):
    page.goto(f"{live_server.url}/ru/calendar/map/")
    page.locator('[data-quick-dates="weekend"]').click()
    saturday = _this_weekend(_today()) + datetime.timedelta(days=7)
    page.locator('#date-nav [data-date-nav="1"]').click()
    expect(page.locator("#map-date-from")).to_have_value(f"{saturday:%Y-%m-%d}")
    expect(page.locator("#map-date-to")).to_have_value(f"{saturday + datetime.timedelta(days=1):%Y-%m-%d}")
    # Not this weekend any more: the quick button lets go.
    expect(page.locator("[data-quick-dates].active")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_the_map_pages_a_season_by_years(page: Page, live_server):
    page.goto(f"{live_server.url}/ru/calendar/map/")
    page.locator('[data-quick-dates="season"]').click()
    page.locator('#date-nav [data-date-nav="-1"]').click()
    year = _today().year - 1
    expect(page.locator("#map-date-from")).to_have_value(f"{year}-01-01")
    expect(page.locator("#map-date-to")).to_have_value(f"{year}-12-31")


@pytest.mark.django_db(transaction=True)
def test_today_brings_the_map_back_to_the_month_ahead(page: Page, live_server):
    page.goto(f"{live_server.url}/ru/calendar/map/")
    page.locator('#date-nav [data-date-nav="1"]').click()
    page.locator('#date-nav [data-date-nav="today"]').click()
    expect(page.locator("#map-date-from")).to_have_value(f"{_today():%Y-%m-%d}")
    expect(page.locator('[data-quick-dates="month"].active')).to_have_count(1)
