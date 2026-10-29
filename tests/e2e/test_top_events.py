"""E2E for top events: first in their day on the calendar, at the head of the list above a divider."""

import datetime

import pytest
from django.utils import timezone
from playwright.sync_api import Page, expect

from calendar_app.models import Competition


def _events(organizer, day):
    for title, top in (("Alpha Ride", False), ("Bravo Ride", False), ("Zeta Race", True)):
        Competition.objects.create(
            title_ru=title,
            title_en=title,
            date_start=day,
            submitted_by=organizer,
            status=Competition.Status.APPROVED,
            is_top=top,
        )


@pytest.mark.django_db(transaction=True)
def test_a_top_event_is_first_in_its_day_on_the_calendar(page: Page, live_server, organizer):
    day = timezone.localdate()
    _events(organizer, day)
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{live_server.url}/en/calendar/")
    titles = page.locator(f".fc-daygrid-day[data-date='{day.isoformat()}'] .fc-event-title")
    expect(titles).to_have_count(3)
    expect(titles.first).to_have_text("Zeta Race")


@pytest.mark.django_db(transaction=True)
def test_the_list_opens_with_the_top_event_marked_and_a_divider_after_it(page: Page, live_server, organizer):
    day = datetime.date(2027, 3, 10)
    _events(organizer, day)
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{live_server.url}/en/calendar/list/?date_from=2027-03-01&date_to=2027-03-31")
    first = page.locator(".calendar-list-table tbody tr").first
    expect(first).to_contain_text("Zeta Race")
    expect(first).to_contain_text("Top event")
    expect(page.locator(".calendar-list-table tbody.calendar-list-rest")).to_be_visible()
    expect(page.locator(".calendar-list-table tbody.calendar-list-rest tr").first).to_contain_text("Alpha Ride")
