"""The period row above the calendar, the list and the map (issue #330).

The calendar counts from the browser's day, so its tests pin the browser's clock to a known Wednesday;
the list and the map count from the site's own day, so theirs work from timezone.localdate().
"""

import calendar
import datetime
import re

import pytest
from django.utils import timezone
from playwright.sync_api import Page, ViewportSize, expect

from calendar_app.models import Competition

WEDNESDAY = datetime.datetime(2026, 10, 21, 12, 0)
SUNDAY = datetime.datetime(2026, 10, 25, 12, 0)
WIDE: ViewportSize = {"width": 1280, "height": 900}


def _calendar(page: Page, live_server, clock=WEDNESDAY, query=""):
    page.clock.set_fixed_time(clock)
    page.set_viewport_size(WIDE)
    page.goto(f"{live_server.url}/en/calendar/{query}")
    expect(page.locator(".fc")).to_be_visible()


def _label(page: Page):
    return page.locator("#period-label")


def _kind(page: Page, kind: str):
    page.locator(f'[data-period-kind="{kind}"]').click()


def _step(page: Page, n: int):
    page.locator(f'[data-period-step="{n}"]').click()


def _race(organizer, title, day):
    return Competition.objects.create(
        title_ru=title,
        title_en=title,
        date_start=day,
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
    )


def _end_of_month(day: datetime.date) -> datetime.date:
    return day.replace(day=calendar.monthrange(day.year, day.month)[1])


# --- The calendar ---


@pytest.mark.django_db(transaction=True)
def test_the_calendar_opens_on_the_month_and_says_so(page: Page, live_server):
    _calendar(page, live_server)
    expect(_label(page)).to_have_text("October 2026")
    expect(page.locator('[data-period-kind="month"]')).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#period-hint")).to_have_text("Arrows: by month \u00b7 tap the month or year")


@pytest.mark.django_db(transaction=True)
def test_today_and_tomorrow_moves_a_day_at_a_time(page: Page, live_server):
    _calendar(page, live_server)
    _kind(page, "days")
    expect(_label(page)).to_have_text("21\u201322 October 2026")
    expect(page.locator(".fc-listRange-view")).to_be_visible()
    _step(page, 1)
    expect(_label(page)).to_have_text("22\u201323 October 2026")


@pytest.mark.django_db(transaction=True)
def test_the_weekend_moves_a_week_at_a_time(page: Page, live_server):
    _calendar(page, live_server)
    _kind(page, "weekend")
    expect(_label(page)).to_have_text("24\u201325 October 2026")
    _step(page, 1)
    expect(_label(page)).to_have_text("31 October \u2013 1 November 2026")


@pytest.mark.django_db(transaction=True)
def test_on_a_sunday_the_weekend_is_the_sunday_and_then_whole_weekends(page: Page, live_server):
    _calendar(page, live_server, clock=SUNDAY)
    _kind(page, "weekend")
    expect(_label(page)).to_have_text("25 October 2026")
    _step(page, 1)
    expect(_label(page)).to_have_text("31 October \u2013 1 November 2026")
    _step(page, -1)
    expect(_label(page)).to_have_text("24\u201325 October 2026")


@pytest.mark.django_db(transaction=True)
def test_the_week_runs_monday_to_sunday(page: Page, live_server):
    _calendar(page, live_server)
    _kind(page, "week")
    expect(_label(page)).to_have_text("19\u201325 October 2026")
    _step(page, 1)
    expect(_label(page)).to_have_text("26 October \u2013 1 November 2026")


@pytest.mark.django_db(transaction=True)
def test_the_week_and_the_weekend_follow_the_site_s_settings(page: Page, live_server, settings):
    """A week from Sunday and a weekend of Friday and Saturday, where the site is used that way (#383)."""
    settings.CALENDAR_FIRST_WEEKDAY = 0
    settings.CALENDAR_WEEKEND = [5, 6]
    _calendar(page, live_server)
    expect(page.locator(".fc-col-header-cell").first).to_have_text("Sun")
    _kind(page, "week")
    expect(_label(page)).to_have_text("18\u201324 October 2026")
    _kind(page, "weekend")
    expect(_label(page)).to_have_text("23\u201324 October 2026")
    _step(page, 1)
    expect(_label(page)).to_have_text("30\u201331 October 2026")


@pytest.mark.django_db(transaction=True)
def test_the_english_grid_starts_its_week_on_the_day_the_period_does(page: Page, live_server):
    _calendar(page, live_server)
    expect(page.locator(".fc-col-header-cell").first).to_have_text("Mon")


@pytest.mark.django_db(transaction=True)
def test_today_keeps_the_kind_and_comes_back(page: Page, live_server):
    _calendar(page, live_server)
    _kind(page, "week")
    _step(page, 1)
    _step(page, 1)
    page.locator("[data-period-today]").click()
    expect(_label(page)).to_have_text("19\u201325 October 2026")


@pytest.mark.django_db(transaction=True)
def test_the_month_picker_pages_its_years_without_moving_the_calendar(page: Page, live_server):
    _calendar(page, live_server)
    page.locator('#period-label [data-period-pick="month"]').click()
    page.locator('[data-pop-year="1"]').click()
    # Paging the years in the picker changes nothing yet.
    expect(_label(page)).to_have_text("October 2026")
    page.locator('[data-pop-month="2"]').click()
    expect(_label(page)).to_have_text("March 2027")
    expect(page.locator("#period-pop")).to_be_hidden()


@pytest.mark.django_db(transaction=True)
def test_the_year_shows_the_whole_year_and_pages_by_years(page: Page, live_server, organizer):
    _race(organizer, "Next spring ride", datetime.date(2027, 3, 10))
    _calendar(page, live_server)
    page.locator('#period-label [data-period-pick="year"]').click()
    page.locator('[data-pop-pick-year="2026"]').click()
    expect(_label(page)).to_have_text("2026, whole year")
    expect(page.locator(".fc-list-event", has_text="Next spring ride")).to_have_count(0)
    _step(page, 1)
    expect(_label(page)).to_have_text("2027, whole year")
    # The events of the period now shown -- paging a list once fetched those of the period before.
    expect(page.locator(".fc-list-event", has_text="Next spring ride")).to_have_count(1)
    _step(page, -1)
    expect(page.locator(".fc-list-event", has_text="Next spring ride")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_paging_back_a_weekend_shows_that_weekends_events(page: Page, live_server, organizer):
    """The empty weekend Artem met: paging a list back fetched the events of the weekend after."""
    _race(organizer, "Last weekend ride", datetime.date(2026, 10, 17))
    _calendar(page, live_server)
    _kind(page, "weekend")
    _step(page, -1)
    expect(_label(page)).to_have_text("17\u201318 October 2026")
    expect(page.locator(".fc-list-event", has_text="Last weekend ride")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_the_month_view_walks_past_the_years_it_lists(page: Page, live_server):
    """An empty calendar lists this year alone -- the arrows can still walk out of it."""
    _calendar(page, live_server)
    for _ in range(13):
        _step(page, -1)
    expect(_label(page)).to_have_text("September 2025")


@pytest.mark.django_db(transaction=True)
def test_a_link_with_dates_opens_on_that_period(page: Page, live_server):
    _calendar(page, live_server, query="?date_from=2027-05-01&date_to=2027-05-02")
    expect(_label(page)).to_have_text("1\u20132 May 2027")
    expect(page.locator('[data-period-kind="weekend"]')).to_have_attribute("aria-pressed", "true")


@pytest.mark.django_db(transaction=True)
def test_the_list_and_map_links_carry_the_period(page: Page, live_server):
    _calendar(page, live_server)
    _kind(page, "week")
    expect(page.locator("#view-link-list")).to_have_attribute(
        "href", re.compile(r"date_from=2026-10-19&date_to=2026-10-25")
    )
    expect(page.locator("#view-link-map")).to_have_attribute(
        "href", re.compile(r"date_from=2026-10-19&date_to=2026-10-25")
    )


@pytest.mark.django_db(transaction=True)
def test_month_from_another_period_opens_the_grid(page: Page, live_server):
    _calendar(page, live_server)
    _kind(page, "week")
    _kind(page, "month")
    expect(page.locator(".fc-dayGridMonth-view")).to_be_visible()
    expect(_label(page)).to_have_text("October 2026")


# --- The list and the map ---


@pytest.mark.django_db(transaction=True)
def test_the_list_opens_on_the_rest_of_this_month(page: Page, live_server):
    today = timezone.localdate()
    page.goto(f"{live_server.url}/en/calendar/list/?reset=1")
    expect(page.locator('#filter-form input[name="date_from"]')).to_have_value(f"{today:%Y-%m-%d}")
    expect(page.locator('#filter-form input[name="date_to"]')).to_have_value(f"{_end_of_month(today):%Y-%m-%d}")
    expect(page.locator('[data-period-kind="month"]')).to_have_attribute("aria-pressed", "true")


@pytest.mark.django_db(transaction=True)
def test_the_list_steps_to_the_whole_next_month(page: Page, live_server):
    today = timezone.localdate()
    first = _end_of_month(today) + datetime.timedelta(days=1)
    page.goto(f"{live_server.url}/en/calendar/list/?reset=1")
    _step(page, 1)
    expect(page).to_have_url(re.compile(f"date_from={first:%Y-%m-%d}&date_to={_end_of_month(first):%Y-%m-%d}"))


@pytest.mark.django_db(transaction=True)
def test_a_filtered_list_runs_on_as_all_upcoming_which_today_keeps(page: Page, live_server, race_event_type):
    page.goto(f"{live_server.url}/en/calendar/list/?event_type={race_event_type.pk}")
    expect(_label(page)).to_contain_text("from")
    expect(page.locator('[data-period-kind="open"]')).to_have_attribute("aria-pressed", "true")
    # Today returns to the current period of the kind on screen (specs/330), and this kind has no last day.
    page.locator("[data-period-today]").click()
    expect(page).to_have_url(re.compile(r"period=upcoming"))
    expect(page.locator('[data-period-kind="open"]')).to_have_attribute("aria-pressed", "true")


@pytest.mark.django_db(transaction=True)
def test_the_map_fills_its_date_fields_from_the_period(page: Page, live_server):
    today = timezone.localdate()
    monday = today - datetime.timedelta(days=today.weekday())
    page.goto(f"{live_server.url}/en/calendar/map/")
    _kind(page, "week")
    expect(page.locator("#map-date-from")).to_have_value(f"{monday:%Y-%m-%d}")
    expect(page.locator("#map-date-to")).to_have_value(f"{monday + datetime.timedelta(days=6):%Y-%m-%d}")
    _step(page, 1)
    expect(page.locator("#map-date-from")).to_have_value(f"{monday + datetime.timedelta(days=7):%Y-%m-%d}")


@pytest.mark.django_db(transaction=True)
def test_a_date_typed_by_hand_is_named_too(page: Page, live_server):
    page.goto(f"{live_server.url}/en/calendar/map/")
    # A phone keeps the native date input; a wide screen hands it to flatpickr.
    page.evaluate(
        """() => {
            const from = document.getElementById('map-date-from');
            const to = document.getElementById('map-date-to');
            const set = (el, v) => { if (el._flatpickr) el._flatpickr.setDate(v, false); else el.value = v; };
            set(from, '2026-06-03');
            set(to, '2026-06-20');
            to.dispatchEvent(new Event('change', {bubbles: true}));
        }"""
    )
    expect(_label(page)).to_have_text("3\u201320 June 2026")
    expect(page.locator("[data-period-kind][aria-pressed=true]")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_kazakh_names_the_period_in_kazakh(page: Page, live_server):
    page.clock.set_fixed_time(WEDNESDAY)
    page.goto(f"{live_server.url}/kk/calendar/")
    expect(_label(page)).not_to_have_text(re.compile("October|M10"))
    expect(_label(page)).to_contain_text("2026")


@pytest.mark.django_db(transaction=True)
def test_on_a_saturday_today_and_tomorrow_stays_itself(page: Page, live_server):
    """Saturday and Sunday are also the weekend; the reader's pick and its one-day step must hold."""
    _calendar(page, live_server, clock=datetime.datetime(2026, 10, 24, 12, 0))
    _kind(page, "days")
    expect(_label(page)).to_have_text("24\u201325 October 2026")
    expect(page.locator('[data-period-kind="days"]')).to_have_attribute("aria-pressed", "true")
    _step(page, 1)
    expect(_label(page)).to_have_text("25\u201326 October 2026")


@pytest.mark.django_db(transaction=True)
def test_the_current_month_travels_as_no_dates(page: Page, live_server):
    """Written out it would pin today: a link shared on the 21st kept opening on the 21st."""
    _calendar(page, live_server)
    expect(page.locator("#view-link-list")).not_to_have_attribute("href", re.compile("date_from"))
    assert "date_from" not in page.evaluate("window.shareUrl()")
    _step(page, 1)
    expect(page.locator("#view-link-list")).to_have_attribute(
        "href", re.compile(r"date_from=2026-11-01&date_to=2026-11-30")
    )


@pytest.mark.django_db(transaction=True)
def test_the_picker_takes_the_keyboard(page: Page, live_server):
    _calendar(page, live_server)
    page.locator('#period-label [data-period-pick="month"]').focus()
    page.keyboard.press("Enter")
    expect(page.locator("#period-pop button:focus")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_a_tap_elsewhere_closes_the_picker(page: Page, live_server):
    """A phone has no Escape key."""
    _calendar(page, live_server)
    page.locator('#period-label [data-period-pick="month"]').click()
    expect(page.locator("#period-pop")).to_be_visible()
    page.locator("h1").click()
    expect(page.locator("#period-pop")).to_be_hidden()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("picker", ["month", "year"])
@pytest.mark.parametrize("choose", [False, True], ids=["escape", "choose"])
def test_closing_the_picker_returns_keyboard_focus(page: Page, live_server, picker, choose):
    _calendar(page, live_server)
    trigger = page.locator(f'#period-label [data-period-pick="{picker}"]')
    trigger.click()
    if choose:
        option = '[data-pop-month="0"]' if picker == "month" else '[data-pop-pick-year="2026"]'
        page.locator(option).click()
    else:
        page.keyboard.press("Escape")
    expect(page.locator("#period-pop")).to_be_hidden()
    expect(trigger).to_be_focused()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "query,expected",
    [
        ("", "2026"),
        ("?date_from=2026-10-25&date_to=2026-10-25", "2026"),
        ("?date_from=2026-10-24&date_to=2026-10-25", "2026"),
        ("?date_from=2026-10-31&date_to=2026-11-01", "2026"),
        ("?date_from=2026-12-31&date_to=2027-01-01", "2026"),
        ("?date_from=2026-10-21", "2026"),
    ],
)
def test_kazakh_period_places_each_year_before_its_days(page: Page, live_server, query, expected):
    page.clock.set_fixed_time(WEDNESDAY)
    page.goto(f"{live_server.url}/kk/calendar/{query}")
    expect(_label(page)).to_contain_text(expected)
    # The year is the first picker in every label, including the open-ended range.
    expect(_label(page).locator("button").first).to_have_attribute("data-period-pick", "year")
    if "2027" in query:
        buttons = _label(page).locator("button")
        expect(buttons.nth(2)).to_have_attribute("data-period-pick", "year")
        expect(buttons.nth(2)).to_have_text("2027")


@pytest.mark.django_db(transaction=True)
def test_reopening_the_calendar_keeps_the_chosen_weekend(page: Page, live_server):
    _calendar(page, live_server)
    _kind(page, "weekend")
    expect(_label(page)).to_have_text("24\u201325 October 2026")
    page.goto(f"{live_server.url}/en/calendar/")
    expect(_label(page)).to_have_text("24\u201325 October 2026")
    expect(page.locator(".fc-listRange-view")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_explicit_links_win_over_the_session_period(page: Page, live_server):
    _calendar(page, live_server)
    _kind(page, "weekend")
    page.goto(f"{live_server.url}/en/calendar/?period=month")
    expect(_label(page)).to_have_text("October 2026")
    assert "period=month" in page.evaluate("window.shareUrl()")
    assert "date_from" not in page.evaluate("window.shareUrl()")
    page.goto(f"{live_server.url}/en/calendar/?date_from=2027-03-01&date_to=2027-03-31")
    expect(_label(page)).to_have_text("March 2027")


@pytest.mark.django_db(transaction=True)
def test_calendar_period_changes_work_when_storage_is_blocked(page: Page, live_server):
    page.add_init_script("Object.defineProperty(window, 'sessionStorage', {get() {throw new Error('blocked');}})")
    _calendar(page, live_server)
    _kind(page, "weekend")
    expect(_label(page)).to_have_text("24\u201325 October 2026")
    assert "date_from=2026-10-24" in page.evaluate("window.shareUrl()")
    expect(page.locator("#view-link-list")).to_have_attribute("href", re.compile("date_from=2026-10-24"))


@pytest.mark.django_db(transaction=True)
def test_a_filtered_month_keeps_its_period_on_the_list(page: Page, live_server, organizer, race_event_type):
    today = timezone.localdate()
    near = _race(organizer, "This month only", today)
    later = _race(organizer, "Another month", _end_of_month(today) + datetime.timedelta(days=1))
    near.event_types.add(race_event_type)
    later.event_types.add(race_event_type)
    _calendar(
        page,
        live_server,
        clock=datetime.datetime.combine(today, datetime.time(12)),
        query=f"?event_type={race_event_type.pk}",
    )
    page.locator("#view-link-list").click()
    expect(page.get_by_role("link", name="This month only").first).to_be_visible()
    expect(page.get_by_role("link", name="Another month")).to_have_count(0)


# --- All upcoming ---


@pytest.mark.django_db(transaction=True)
def test_all_upcoming_on_the_list_has_no_last_day_and_its_arrows_step_nowhere(page: Page, live_server, organizer):
    today = timezone.localdate()
    _race(organizer, "Next season", today + datetime.timedelta(days=200))
    page.set_viewport_size(WIDE)
    page.goto(f"{live_server.url}/en/calendar/list/")
    expect(page.get_by_role("link", name="Next season")).to_have_count(0)
    _kind(page, "open")
    page.wait_for_url(re.compile(r"period=upcoming"))
    expect(page.get_by_role("link", name="Next season").first).to_be_visible()
    expect(_label(page)).to_have_text(re.compile(rf"^from {today.day} \w+ {today.year}$"))
    expect(page.locator('[data-period-kind="open"]')).to_have_attribute("aria-pressed", "true")
    for n in (-1, 1):
        expect(page.locator(f'[data-period-step="{n}"]')).to_be_disabled()
    # Another tab opens on every day ahead too, from the day it is opened on.
    expect(page.locator("#view-link-map")).to_have_attribute("href", re.compile(r"period=upcoming"))
    expect(page.locator("#view-link-map")).not_to_have_attribute("href", re.compile(r"date_from"))
    assert "date_from" not in page.evaluate("window.shareUrl()")
    # A month picked next is a month again.
    _kind(page, "month")
    page.wait_for_url(lambda url: "period=upcoming" not in url)
    expect(page.get_by_role("link", name="Next season")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_all_upcoming_on_the_calendar_lists_every_day_ahead(page: Page, live_server, organizer):
    _race(organizer, "Next season", WEDNESDAY.date() + datetime.timedelta(days=200))
    _calendar(page, live_server)
    _kind(page, "open")
    expect(page.locator(".fc-listRange-view")).to_be_visible()
    expect(page.locator(".fc-list-event-title", has_text="Next season")).to_be_visible()
    expect(_label(page)).to_have_text("from 21 October 2026")
    share = page.evaluate("window.shareUrl()")
    assert "period=upcoming" in share and "date_from" not in share, share
    expect(page.locator("#view-link-list")).to_have_attribute("href", re.compile(r"period=upcoming"))
    _kind(page, "month")
    expect(page.locator(".fc-dayGridMonth-view")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_a_link_to_all_upcoming_opens_the_calendar_on_it(page: Page, live_server, organizer):
    _race(organizer, "Next season", WEDNESDAY.date() + datetime.timedelta(days=200))
    _calendar(page, live_server, query="?period=upcoming")
    expect(_label(page)).to_have_text("from 21 October 2026")
    expect(page.locator('[data-period-kind="open"]')).to_have_attribute("aria-pressed", "true")
    expect(page.locator(".fc-list-event-title", has_text="Next season")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_all_upcoming_on_the_map_leaves_the_last_day_empty(page: Page, live_server):
    page.set_viewport_size(WIDE)
    page.goto(f"{live_server.url}/en/calendar/map/")
    _kind(page, "open")
    expect(page.locator("#map-date-to")).to_have_value("")
    expect(_label(page)).to_have_text(re.compile(r"^from "))
    expect(page.locator("#view-link-list")).to_have_attribute("href", re.compile(r"period=upcoming"))
