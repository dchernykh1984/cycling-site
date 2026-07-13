"""E2E tests for the sticky site header."""

import pytest
from playwright.sync_api import Page, expect

_TRANSPARENT = ("rgba(0, 0, 0, 0)", "transparent")


@pytest.mark.django_db(transaction=True)
def test_sticky_navbar_has_a_solid_background(page: Page, live_server):
    """The sticky header must have an opaque background so scrolled content cannot show through it."""
    page.goto(f"{live_server.url}/calendar/")
    navbar = page.locator("nav.navbar")
    expect(navbar).to_be_visible()
    background = navbar.evaluate("el => getComputedStyle(el).backgroundColor")
    assert background not in _TRANSPARENT, f"navbar background is see-through: {background!r}"
