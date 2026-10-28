"""Add to calendar on an event's page (issue #398), as a reader sees and taps it.

The button stands beside "Share" and looks like it in every skin; it leads to the event's own
calendar file, which the reader's calendar offers to add.
"""

import pytest
from django.utils.translation import gettext
from django.utils.translation import override as translation_override
from playwright.sync_api import Page, expect

from calendar_app.models import Competition
from tests.e2e.conftest import UPCOMING
from tests.e2e.contrast import legibility
from tests.e2e.test_interface_rules import _REACH
from tests.e2e.test_skin_contrast import _in_state


@pytest.fixture
def race(db, organizer):
    return Competition.objects.create(
        title_ru="E2E calendar race", date_start=UPCOMING, submitted_by=organizer, status=Competition.Status.APPROVED
    )


def _open(page: Page, live_server, race):
    page.goto(f"{live_server.url}/ru/calendar/{race.pk}/")
    return page.locator(".calendar-btn"), page.locator(".share-btn")


@pytest.mark.django_db(transaction=True)
def test_beside_share_it_leads_to_the_event_s_calendar_file(page: Page, live_server, race):
    button, share = _open(page, live_server, race)
    expect(button).to_be_visible()
    # In the heading's row, right after Share
    sb, bb = share.bounding_box(), button.bounding_box()
    assert sb is not None and bb is not None
    assert bb["y"] < sb["y"] + sb["height"] and bb["y"] + bb["height"] > sb["y"], (sb, bb)
    assert bb["x"] >= sb["x"] + sb["width"], (sb, bb)
    response = page.request.get(f"{live_server.url}{button.get_attribute('href')}")
    assert response.status == 200
    assert response.headers["content-type"].startswith("text/calendar")
    assert "SUMMARY:E2E calendar race" in response.text()


@pytest.mark.django_db(transaction=True)
def test_on_a_phone_it_is_an_icon_the_size_of_share_that_a_tap_reaches_across_44px(page: Page, live_server, race):
    page.set_viewport_size({"width": 360, "height": 740})
    button, share = _open(page, live_server, race)
    # The word folds away as Share's does, and the button is still named in words
    expect(button.locator("span")).to_be_hidden()
    with translation_override("ru"):
        expect(button).to_have_attribute("aria-label", gettext("Add to calendar"))
    sb, bb = share.bounding_box(), button.bounding_box()
    assert sb is not None and bb is not None
    assert abs(sb["width"] - bb["width"]) < 1 and abs(sb["height"] - bb["height"]) < 1, (sb, bb)
    page.mouse.move(0, 0)
    wide, high = button.evaluate(_REACH)
    assert wide >= 44 and high >= 44, (wide, high)
    # Its zone stops short of Share: a tap on Share still shares
    share_wide, _ = share.evaluate(_REACH)
    assert share_wide >= sb["width"] - 1, (share_wide, sb)


@pytest.mark.django_db(transaction=True)
def test_it_reads_as_the_share_button_beside_it(page: Page, live_server, race):
    button, share = _open(page, live_server, race)
    for state in ("rest", "hover", "focus"):
        _in_state(page, share, state)
        expected = legibility(share)
        _in_state(page, button, state)
        assert legibility(button) == pytest.approx(expected, abs=0.05), state
