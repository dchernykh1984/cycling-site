"""E2E tests for the filter date pickers (flatpickr) on the list/map views.

The popup must start the week on the same day as the main calendar, in every language: the day
settings.CALENDAR_FIRST_WEEKDAY names, Monday unless set otherwise (issue #383).
On mobile the native date picker is kept by design, so the test skips there.
"""

import re

import pytest
from playwright.sync_api import Page

_MOBILE = re.compile(r"Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini", re.I)
_READY = "() => { const el = document.querySelector('input.js-date-filter'); return !!(el && el._flatpickr); }"


def _first_day_of_week_or_skip(page: Page, url: str) -> int:
    page.goto(url)
    if _MOBILE.search(page.evaluate("() => navigator.userAgent")):
        pytest.skip("mobile keeps the native date picker (first day is OS-controlled by design)")
    page.wait_for_function(_READY)
    picker = page.locator("input.js-date-filter").first
    return picker.evaluate("el => el._flatpickr.l10n.firstDayOfWeek")


@pytest.mark.django_db(transaction=True)
def test_filter_datepicker_starts_on_monday_for_ru(page: Page, live_server):
    assert _first_day_of_week_or_skip(page, f"{live_server.url}/ru/calendar/list/") == 1  # Monday


@pytest.mark.django_db(transaction=True)
def test_filter_datepicker_starts_on_monday_for_en_too(page: Page, live_server):
    assert _first_day_of_week_or_skip(page, f"{live_server.url}/en/calendar/list/") == 1  # Monday


@pytest.mark.django_db(transaction=True)
def test_filter_datepicker_follows_the_site_s_first_day(page: Page, live_server, settings):
    settings.CALENDAR_FIRST_WEEKDAY = 0
    assert _first_day_of_week_or_skip(page, f"{live_server.url}/ru/calendar/map/") == 0  # Sunday
