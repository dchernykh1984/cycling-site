"""The month as a list of days, the way a phone opens it (issue #330)."""

import datetime

import pytest
from django.utils.translation import override as translation_override
from playwright.sync_api import Page, expect

from calendar_app.models import Competition
from calendar_app.views import calendar_date_words

TODAY = datetime.date.today()
# The current month opens at today; the first of the month is folded away behind a button.
FIRST = TODAY.replace(day=1)


@pytest.fixture
def three_day_race(db, organizer):
    return Competition.objects.create(
        title_ru="Three day race",
        date_start=TODAY,
        date_end=TODAY + datetime.timedelta(days=2),
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
    )


def _open_list(page: Page, live_server, language="ru"):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{live_server.url}/{language}/calendar/")
    expect(page.locator(".fc-listMonth-view")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_a_multi_day_race_is_one_row_with_the_day_it_ends(page: Page, live_server, three_day_race):
    _open_list(page, live_server)
    rows = page.locator(".fc-list-event:visible", has_text="Three day race")
    expect(rows).to_have_count(1)
    last = TODAY + datetime.timedelta(days=2)
    with translation_override("ru"):
        month = calendar_date_words()["months"][last.month - 1]
    expect(rows.first).to_contain_text(f"{last.day} {month}")


@pytest.mark.django_db(transaction=True)
def test_a_day_holding_only_a_repeat_loses_its_heading(page: Page, live_server, three_day_race):
    """The race's second and third days had nothing else on them: no empty headings left behind."""
    _open_list(page, live_server)
    expect(page.locator(".fc-list-day:visible")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_kazakh_day_headings_come_from_the_catalogue(page: Page, live_server, three_day_race):
    """Browsers write these as '2026 M10 1 THU'; the site's own names read as Kazakh."""
    _open_list(page, live_server, "kk")
    with translation_override("kk"):
        words = calendar_date_words()
    heading = page.locator(".fc-list-day:visible").first
    expect(heading).to_contain_text(f"{TODAY.day} {words['months'][TODAY.month - 1]}")
    expect(heading).not_to_contain_text(" M")


@pytest.mark.django_db(transaction=True)
def test_the_list_has_no_empty_time_column(page: Page, live_server, three_day_race):
    """Every event is all-day; the column used to say "all-day" in English on every row."""
    _open_list(page, live_server)
    expect(page.locator(".fc-list-event-time:visible")).to_have_count(0)
    expect(page.locator(".fc-listMonth-view")).not_to_contain_text("all-day")


@pytest.fixture
def earlier_and_today(db, organizer):
    if TODAY.day == 1:
        pytest.skip("no earlier day in the month on the 1st")
    for title, start, end in (
        ("Earlier ride", FIRST, None),
        ("Running since earlier", FIRST, TODAY + datetime.timedelta(days=1)),
        ("Today ride", TODAY, None),
    ):
        Competition.objects.create(
            title_ru=title,
            date_start=start,
            date_end=end,
            submitted_by=organizer,
            status=Competition.Status.APPROVED,
        )


@pytest.mark.django_db(transaction=True)
def test_the_current_month_starts_at_today(page: Page, live_server, earlier_and_today):
    """On the 20th nobody opens a phone calendar to read the 1st; the earlier days fold away."""
    _open_list(page, live_server)
    expect(page.locator(".fc-list-day:visible").first).to_have_attribute("data-date", f"{TODAY:%Y-%m-%d}")
    expect(page.locator(".fc-list-event:visible", has_text="Earlier ride")).to_have_count(0)
    expect(page.locator(".fc-list-past-toggle button")).to_contain_text("(1)")


@pytest.mark.django_db(transaction=True)
def test_a_race_still_running_shows_under_today(page: Page, live_server, earlier_and_today):
    _open_list(page, live_server)
    expect(page.locator(".fc-list-event:visible", has_text="Running since earlier")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_the_earlier_days_open_with_one_tap(page: Page, live_server, earlier_and_today):
    _open_list(page, live_server)
    page.locator(".fc-list-past-toggle button").click()
    expect(page.locator(".fc-list-day:visible").first).to_have_attribute("data-date", f"{FIRST:%Y-%m-%d}")
    expect(page.locator(".fc-list-event:visible", has_text="Earlier ride")).to_have_count(1)
    expect(page.locator(".fc-list-past-toggle")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_a_past_month_is_read_whole(page: Page, live_server, organizer):
    """Only the month holding today folds; a month gone by would otherwise show just the button."""
    Competition.objects.create(
        title_ru="Last month ride",
        date_start=FIRST - datetime.timedelta(days=10),
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
    )
    _open_list(page, live_server)
    page.locator('[data-period-step="-1"]').click()
    expect(page.locator(".fc-list-event:visible", has_text="Last month ride")).to_have_count(1)
    expect(page.locator(".fc-list-past-toggle")).to_have_count(0)


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
    page.goto(f"{live_server.url}/en/calendar/")
    row = page.locator(".fc-list-event:visible", has_text="Spring race")
    expect(row.locator(".fc-list-event-until")).to_have_text("\u2013 28 March")
    context.close()


@pytest.mark.django_db(transaction=True)
def test_opening_the_earlier_days_keeps_the_keyboard_in_the_list(page: Page, live_server, earlier_and_today):
    _open_list(page, live_server)
    page.locator(".fc-list-past-toggle button").focus()
    page.keyboard.press("Enter")
    expect(page.locator("#calendar .fc-list-event a:focus")).to_have_count(1)
