"""An event's description fits a phone, however long its words.

An announcement imported from a chat names its source, and the chat "Almaty,gory,kafe,pikniki,..."
writes its name with commas and no spaces: forty letters without a break, wider than a 360px
phone, so the event's page scrolled sideways. An article's body already broke such words.
"""

import pytest
from playwright.sync_api import Page

from calendar_app.models import Competition
from tests.e2e.conftest import UPCOMING

# Forty letters with commas and no spaces, as the chat writes its name.
LONG_WORD = "Almaty,mountains,cafe,picnics,trips,boardgames"


@pytest.fixture
def ride(db, organizer):
    description = f"<p>A hike to the peak.</p><p>Announcement source: {LONG_WORD}</p>"
    return Competition.objects.create(
        title_ru="E2E long word",
        description_ru=description,
        description_kk=description,
        description_en=description,
        date_start=UPCOMING,
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("language", ["ru", "kk", "en"])
def test_a_long_word_in_a_description_never_scrolls_a_phone_sideways(page: Page, live_server, ride, language):
    for width in (320, 360):
        page.set_viewport_size({"width": width, "height": 640})
        page.goto(f"{live_server.url}/{language}/calendar/{ride.pk}/")
        assert page.locator("main .competition-description").inner_text().count(LONG_WORD[:20]) == 1
        assert page.evaluate("document.documentElement.scrollWidth") <= width, width
