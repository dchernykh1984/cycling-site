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
def test_month_stays_lit_when_the_reader_is_a_day_behind_the_site(page: Page, live_server):
    """The list counts from the site's day, not the browser's: late evening west of Almaty."""
    from django.utils import timezone

    yesterday = timezone.localdate() - datetime.timedelta(days=1)
    page.clock.set_fixed_time(datetime.datetime(yesterday.year, yesterday.month, yesterday.day, 22, 0))
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


@pytest.mark.django_db(transaction=True)
def test_on_a_sunday_the_arrow_moves_to_the_next_saturday_and_sunday(page: Page, live_server):
    """On a Sunday "this weekend" is the Sunday alone; a week on is still a Saturday and a Sunday."""
    page.clock.set_fixed_time(datetime.datetime(2026, 10, 25, 12, 0))
    page.goto(f"{live_server.url}/en/calendar/")
    page.locator('[data-quick-dates="weekend"]').click()
    expect(page.locator(".fc-toolbar-title")).to_have_text("25 October")
    page.locator(".fc-next-button").click()
    expect(page.locator(".fc-toolbar-title")).to_have_text("31 October \u2013 1 November")
    page.locator(".fc-prev-button").click()
    expect(page.locator(".fc-toolbar-title")).to_have_text("24\u201325 October")


@pytest.mark.django_db(transaction=True)
def test_the_links_follow_the_range_on_screen(page: Page, live_server):
    """Paged to the next weekend, the List link carries it; back on the month, it carries none."""
    page.clock.set_fixed_time(datetime.datetime(2026, 10, 21, 12, 0))
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{live_server.url}/en/calendar/")
    page.locator('[data-quick-dates="weekend"]').click()
    page.locator(".fc-next-button").click()
    link = page.locator("#view-link-list")
    expect(link).to_have_attribute("href", re.compile(r"date_from=2026-10-31&date_to=2026-11-01"))
    page.locator(".fc-dayGridMonth-button").click()
    expect(link).not_to_have_attribute("href", re.compile(r"date_from"))


@pytest.mark.django_db(transaction=True)
def test_a_date_changed_by_hand_on_the_map_unlights_the_button(page: Page, live_server):
    page.goto(f"{live_server.url}/ru/calendar/map/")
    page.locator('[data-quick-dates="season"]').click()
    expect(page.locator('[data-quick-dates="season"].active')).to_have_count(1)
    # A phone keeps the native date input; a wide screen hands it to flatpickr.
    page.evaluate(
        """() => {
            const el = document.getElementById('map-date-to');
            if (el._flatpickr) { el._flatpickr.setDate('2026-06-30', true); return; }
            el.value = '2026-06-30';
            el.dispatchEvent(new Event('change', {bubbles: true}));
        }"""
    )
    expect(page.locator("[data-quick-dates].active")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_month_on_the_month_already_shown_lets_go_on_the_next_page(page: Page, live_server):
    """Month on the month already on screen changes no range; paging on must still leave it."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{live_server.url}/en/calendar/")
    page.locator('[data-quick-dates="month"]').click()
    expect(page.locator('[data-quick-dates="month"].active')).to_have_count(1)
    page.locator(".fc-next-button").click()
    expect(page.locator("[data-quick-dates].active")).to_have_count(0)
    expect(page.locator("#view-link-list")).not_to_have_attribute("href", re.compile(r"date_from"))
