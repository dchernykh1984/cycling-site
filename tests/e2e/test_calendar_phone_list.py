"""The month as a list of days, the way a phone opens it (issue #330)."""

import datetime

import pytest
from django.utils.translation import override as translation_override
from playwright.sync_api import Page, expect

from calendar_app.models import Competition
from calendar_app.views import calendar_date_words

TODAY = datetime.date.today()
# Inside the current month, so the list shows it without paging.
FIRST = TODAY.replace(day=1)


@pytest.fixture
def three_day_race(db, organizer):
    return Competition.objects.create(
        title_ru="Three day race",
        date_start=FIRST,
        date_end=FIRST + datetime.timedelta(days=2),
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
    last = FIRST + datetime.timedelta(days=2)
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
    expect(heading).to_contain_text(f"{FIRST.day} {words['months'][FIRST.month - 1]}")
    expect(heading).not_to_contain_text(" M")


@pytest.mark.django_db(transaction=True)
def test_the_list_has_no_empty_time_column(page: Page, live_server, three_day_race):
    """Every event is all-day; the column used to say "all-day" in English on every row."""
    _open_list(page, live_server)
    expect(page.locator(".fc-list-event-time:visible")).to_have_count(0)
    expect(page.locator(".fc-listMonth-view")).not_to_contain_text("all-day")
