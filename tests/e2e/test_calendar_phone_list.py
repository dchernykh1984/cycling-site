"""Lists of days (issue #330): the List tab on a phone, and a short period on the calendar.

A phone reads the List tab by day -- the day, then the events that start on it -- where a wide
screen keeps the table. The calendar initially lists days on a phone; Month opens its grid, and
a short period (a weekend, a week) is a list of exactly those days.
"""

import datetime

import pytest
from django.urls import reverse
from django.utils.translation import override as translation_override
from playwright.sync_api import Page, expect

from calendar_app.models import Competition, EventType
from calendar_app.views import calendar_date_words
from locations.models import Location

TODAY = datetime.date.today()


@pytest.fixture
def three_day_race(db, organizer):
    return Competition.objects.create(
        title_ru="Three day race",
        title_kk="Three day race",
        date_start=TODAY,
        date_end=TODAY + datetime.timedelta(days=2),
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
    )


def _month_day(day, language="ru"):
    with translation_override(language):
        return f"{day.day} {calendar_date_words()['months'][day.month - 1]}"


@pytest.mark.django_db(transaction=True)
def test_a_phone_reads_the_list_tab_by_day(page: Page, live_server, three_day_race):
    """A table of ten columns does not read on a phone; the same rows by day do."""
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{live_server.url}/ru/calendar/list/")
    expect(page.locator(".calendar-days")).to_be_visible()
    expect(page.locator(".calendar-list-table")).to_be_hidden()
    expect(page.locator(".calendar-day").first).to_contain_text(_month_day(TODAY))


@pytest.mark.django_db(transaction=True)
def test_a_wide_screen_keeps_the_table(page: Page, live_server, three_day_race):
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{live_server.url}/ru/calendar/list/")
    expect(page.locator(".calendar-list-table")).to_be_visible()
    expect(page.locator(".calendar-days")).to_be_hidden()


@pytest.mark.django_db(transaction=True)
def test_a_multi_day_race_is_one_row_with_the_day_it_ends(page: Page, live_server, three_day_race):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{live_server.url}/ru/calendar/list/")
    rows = page.locator(".calendar-day-events li", has_text="Three day race")
    expect(rows).to_have_count(1)
    expect(rows.first.locator(".calendar-day-until")).to_contain_text(_month_day(TODAY + datetime.timedelta(days=2)))


@pytest.mark.django_db(transaction=True)
def test_kazakh_day_headings_come_from_the_catalogue(page: Page, live_server, three_day_race):
    """Browsers write these as '2026 M10 1 THU'; the site's own names read as Kazakh."""
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{live_server.url}/kk/calendar/list/")
    heading = page.locator(".calendar-day").first
    expect(heading).to_contain_text(_month_day(TODAY, "kk"))
    expect(heading).not_to_contain_text(" M")


@pytest.mark.django_db(transaction=True)
def test_a_week_on_the_calendar_shows_a_multi_day_race_once(page: Page, live_server, three_day_race):
    """A short period on the calendar is a list of its days; a race running over several of them is
    one row on its first day, and a day holding only a repeat loses its heading too."""
    page.set_viewport_size({"width": 390, "height": 844})
    end = TODAY + datetime.timedelta(days=6)
    page.goto(f"{live_server.url}/ru/calendar/?date_from={TODAY:%Y-%m-%d}&date_to={end:%Y-%m-%d}")
    rows = page.locator(".fc-list-event:visible", has_text="Three day race")
    expect(rows).to_have_count(1)
    expect(page.locator(".fc-list-day:visible")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_the_end_day_holds_where_clocks_go_forward(browser, live_server, organizer):
    """Europe moves its clocks on 28 March 2027; a race over the 27th-28th still ends on the 28th."""
    Competition.objects.create(
        title_en="Spring race",
        title_ru="Spring race",
        date_start=datetime.date(2027, 3, 27),
        date_end=datetime.date(2027, 3, 28),
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
    )
    context = browser.new_context(timezone_id="Europe/Berlin", viewport={"width": 390, "height": 844})
    page = context.new_page()
    page.clock.set_fixed_time(datetime.datetime(2027, 3, 20, 12, 0))
    page.goto(f"{live_server.url}/en/calendar/?date_from=2027-03-22&date_to=2027-03-28")
    row = page.locator(".fc-list-event:visible", has_text="Spring race")
    # The race has a row on each of its two days until the list folds the second one away, a beat
    # after the rows are drawn; judge the end day on the one row left.
    expect(row).to_have_count(1)
    expect(row.locator(".fc-list-event-until")).to_have_text("\u2013 28 March")
    context.close()


@pytest.mark.django_db(transaction=True)
def test_phone_rows_keep_their_sport_place_and_information(page: Page, live_server, three_day_race, road_discipline):
    parent = None
    for name in ("Demo country", "Demo region", "Demo city", "Demo venue"):
        names = dict(name=name, name_ru=name, name_kk=name, name_en=name)
        parent = parent.add_child(**names) if parent else Location.add_root(**names)
    three_day_race.location = parent
    three_day_race.url_announcement = "https://example.com/information"
    three_day_race.url_registration = "https://example.com/register"
    three_day_race.registration_enabled = True
    three_day_race.save()
    three_day_race.disciplines.add(road_discipline)
    three_day_race.event_types.add(EventType.objects.create(name_en="Demo type", name_ru="Demo type"))
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{live_server.url}/en/calendar/list/")
    row = page.locator(".calendar-day-events li", has_text="Three day race")
    expect(row.locator(".calendar-event-summary")).to_contain_text("Demo city")
    expect(row.locator(".calendar-event-summary")).to_contain_text("Road Race")
    row.locator("summary").click()
    for fact in ("Demo type", "Road Cycling", "Road Race", "Demo country", "Demo region", "Demo venue"):
        expect(row.locator("details")).to_contain_text(fact)
    expect(row.get_by_role("link", name="Info", exact=True)).to_have_attribute(
        "href", "https://example.com/information"
    )
    with translation_override("en"):
        register_url = reverse("registrations:register", args=[three_day_race.pk])
    expect(row.get_by_role("link", name="Register", exact=True)).to_have_attribute("href", register_url)
