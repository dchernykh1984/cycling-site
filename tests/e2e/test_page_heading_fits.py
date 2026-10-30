"""A page's heading and its share button fit a phone, whatever the language.

The Russian privacy policy's heading carries "konfidentsialnosti", a word wider than a 360px phone
leaves beside the share button: the button was pushed past the screen and the page scrolled
sideways. The event page had been fixed for the same reason; the other headings with a page action
had not.
"""

import pytest
from playwright.sync_api import Page

# Views of their own; the Wagtail pages (map, knowledge base) need fixtures of their own in this suite.
PAGES = ("privacy/", "terms/", "news/", "search/")


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("language", ["ru", "kk", "en"])
def test_a_heading_never_pushes_its_share_button_off_a_phone(page: Page, live_server, language):
    page.set_viewport_size({"width": 320, "height": 640})
    for path in PAGES:
        page.goto(f"{live_server.url}/{language}/{path}")
        assert page.evaluate("document.documentElement.scrollWidth") <= 320, path
        share = page.locator("main .share-btn")
        assert share.count() == 1, path
        box = share.bounding_box()
        assert box is not None and box["x"] + box["width"] <= 320, (path, box)
