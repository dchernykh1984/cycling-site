"""A member's account menu stays on screen on a laptop, in the skin the suite runs in.

Light and dark are the maintainer's and kept as they are (2026-10-21): their navbar is wider than a
1280 or 1366 px window and scrolls sideways there. A designer's skin gets no such allowance.
"""

import pytest
from django.conf import settings
from playwright.sync_api import Page

from accounts.models import User
from tests.e2e.conftest import inject_session

KNOWN_OVERFLOW = {"light", "dark"}


@pytest.mark.parametrize("width", [1280, 1366])
@pytest.mark.django_db(transaction=True)
def test_the_account_menu_stays_on_screen(page: Page, live_server, width):
    if settings.DEFAULT_SKIN in KNOWN_OVERFLOW:
        pytest.skip(f"the {settings.DEFAULT_SKIN} navbar is kept as it is")
    # A long address, as real ones are: the button that shows it is what used to fall off the edge.
    member = User.objects.create_user(
        username="navbar.width.check.long@example.com",
        email="navbar.width.check.long@example.com",
        role=User.Role.ADMIN,
    )
    page.set_viewport_size({"width": width, "height": 900})
    inject_session(page, live_server, member)
    page.goto(f"{live_server.url}/ru/calendar/")

    account = page.locator("nav.navbar .dropdown-toggle").last
    box = account.bounding_box()
    assert box is not None and box["x"] + box["width"] <= width, box
    assert page.evaluate("document.documentElement.scrollWidth") <= width
