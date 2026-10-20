"""A busy day in the month grid (issue #330).

A Saturday in season holds twenty events, and a cell that grows to fit them all stretched the month
over several screens on a phone. The grid shows three and a "+N" that opens the rest.
"""

import datetime

import pytest
from django.utils.translation import override as translation_override
from playwright.sync_api import Page, expect

from calendar_app.models import Competition
from calendar_app.views import calendar_date_words

TODAY = datetime.date.today()


@pytest.fixture
def busy_day(db, organizer):
    for n in range(5):
        Competition.objects.create(
            title_ru=f"Busy day race {n}",
            date_start=TODAY,
            submitted_by=organizer,
            status=Competition.Status.APPROVED,
        )


@pytest.mark.django_db(transaction=True)
def test_a_busy_day_shows_three_and_a_count(page: Page, live_server, busy_day):
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{live_server.url}/ru/calendar/")
    cell = page.locator(f'.fc-daygrid-day[data-date="{TODAY:%Y-%m-%d}"]')
    expect(cell.locator(".fc-daygrid-more-link")).to_have_text("+2")
    expect(cell.locator(".fc-daygrid-event-harness:not(.fc-daygrid-event-harness-abs) .fc-event")).to_have_count(3)


@pytest.mark.django_db(transaction=True)
def test_the_count_opens_every_event_of_the_day(page: Page, live_server, busy_day):
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{live_server.url}/ru/calendar/")
    page.locator(f'.fc-daygrid-day[data-date="{TODAY:%Y-%m-%d}"] .fc-daygrid-more-link').click()
    popover = page.locator(".fc-popover")
    for n in range(5):
        expect(popover).to_contain_text(f"Busy day race {n}")
    # The heading is written from the site's own month names, not the browser's.
    with translation_override("ru"):
        month = calendar_date_words()["months"][TODAY.month - 1]
    expect(popover.locator(".fc-popover-title")).to_contain_text(f"{TODAY.day} {month},")
