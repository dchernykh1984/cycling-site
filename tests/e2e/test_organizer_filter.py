"""E2E for the calendar's organizer filter (issue #336): picked from a searchable list of boxes like the
places, it leaves the list with every event of the organizer, past and to come, and says whose they are;
an organizer's name on the Ratings tab opens the same list."""

import datetime
import re

import pytest
from playwright.sync_api import Page, expect

from accounts.models import User
from calendar_app.models import Competition
from ratings import form
from ratings.models import Review
from tests.e2e.conftest import open_filter_panel

TODAY = datetime.date.today()


@pytest.fixture
def pavel(db):
    return User.objects.create_user(
        username="pavel",
        email="pavel@test.local",
        password="testpass123!",
        role=User.Role.ORGANIZER,
        first_name="Pavel",
        last_name="Melnikov",
    )


def _event(title, days, author):
    return Competition.objects.create(
        title_ru=title,
        title_en=title,
        date_start=TODAY + datetime.timedelta(days=days),
        submitted_by=author,
        status=Competition.Status.APPROVED,
    )


def _events(pavel, organizer):
    _event("Somebody else's race", 2, organizer)
    return _event("Last year's race", -300, pavel), _event("Next year's race", 200, pavel)


def _shows_only_pavels(page: Page):
    # A phone and a desktop each draw the list their own way; the one on screen is the visible one
    for title in ("Last year's race", "Next year's race"):
        expect(page.locator("main a:visible", has_text=title).first).to_be_visible()
    expect(page.locator("main a", has_text="Somebody else's race")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_an_organizer_picked_in_the_filter_leaves_all_their_events_past_and_to_come(
    page: Page, live_server, pavel, organizer
):
    _events(pavel, organizer)
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{live_server.url}/en/calendar/list/")
    open_filter_panel(page)
    page.click("#og-btn-1")
    page.locator("#og-menu-1 .mf-search").fill("Meln")
    page.locator(f"#og-menu-1 li.mf-item-row input[value='{pavel.pk}']").check()
    expect(page).to_have_url(re.compile(rf"organizer={pavel.pk}"))
    _shows_only_pavels(page)
    expect(page.locator("#og-btn-1 .mf-text")).to_have_text("Melnikov Pavel")
    # On a phone the panel folds away, and the chip says whose events these are
    page.set_viewport_size({"width": 360, "height": 800})
    expect(page.locator("#filter-chips")).to_contain_text("Organizer: Melnikov Pavel")


@pytest.mark.django_db(transaction=True)
def test_an_organizers_name_on_the_ratings_tab_opens_all_their_events(page: Page, live_server, pavel, organizer):
    for event in _events(pavel, organizer):
        for score in (4, 5):
            Review.objects.create(competition=event, form=form.VERSION, answers={form.RATED: score})
    page.goto(f"{live_server.url}/en/ratings/")
    page.get_by_role("link", name="Pavel Melnikov").click()
    expect(page).to_have_url(re.compile(rf"/en/calendar/list/\?organizer={pavel.pk}$"))
    _shows_only_pavels(page)
