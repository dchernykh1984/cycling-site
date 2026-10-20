"""The share button (issue #327), as a reader uses it.

The system share sheet is replaced with a stand-in that records what it was handed, so the tests
check the very link the reader would send, in every browser.
"""

import re

import pytest
from playwright.sync_api import Page, expect

from calendar_app.models import Competition
from tests.e2e.conftest import UPCOMING, inject_session

RECORD_SHARE = "navigator.share = (data) => { window.__shared = data; return Promise.resolve(); };"
NO_SHARE_SHEET = (
    "delete Navigator.prototype.share; navigator.share = undefined;"
    "navigator.clipboard.writeText = (t) => { window.__copied = t; return Promise.resolve(); };"
)


@pytest.mark.django_db(transaction=True)
def test_the_calendar_is_shared_with_its_filters(page: Page, live_server, race_event_type):
    page.add_init_script(RECORD_SHARE)
    page.goto(f"{live_server.url}/ru/calendar/?event_type={race_event_type.pk}")
    page.wait_for_load_state("load")

    button = page.locator(".share-btn").first
    heading = page.locator("h1").first
    expect(button).to_be_visible()
    # Beside the heading, not tucked away in a menu: on a phone too.
    hb, bb = heading.bounding_box(), button.bounding_box()
    assert hb is not None and bb is not None
    assert bb["y"] < hb["y"] + hb["height"] and bb["y"] + bb["height"] > hb["y"], (hb, bb)

    button.click()
    shared = page.evaluate("window.__shared")
    assert re.search(rf"/ru/calendar/\?.*event_type={race_event_type.pk}", shared["url"]), shared
    assert "favorite" not in shared["url"]


@pytest.mark.django_db(transaction=True)
def test_an_invite_only_event_is_shared_as_its_invitation(page: Page, live_server, organizer):
    event = Competition.objects.create(
        title_ru="E2E Private",
        date_start=UPCOMING,
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
        invite_only=True,
    )
    page.add_init_script(RECORD_SHARE)
    inject_session(page, live_server, organizer)
    page.goto(f"{live_server.url}/ru/calendar/{event.pk}/")
    page.locator(".share-btn").click()
    assert page.evaluate("window.__shared")["url"].endswith(f"/ru/calendar/{event.pk}/invite/{event.invite_key}/")


@pytest.mark.django_db(transaction=True)
def test_without_a_share_sheet_the_link_is_copied(page: Page, live_server):
    page.add_init_script(NO_SHARE_SHEET)
    page.goto(f"{live_server.url}/ru/news/")
    button = page.locator(".share-btn")
    button.click()
    assert page.evaluate("window.__copied").endswith("/ru/news/")
    label = button.locator(".share-label")
    expect(label).to_have_text(button.get_attribute("data-copied-label") or "")
    # Seen, not only set: on a phone the button is an icon, and the word has to appear beside it.
    expect(label).to_be_visible()
