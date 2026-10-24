"""The skin on offer (settings.SKIN_OFFER), in a browser: one tap switches to it, and it is not asked again."""

import pytest
from django.utils.translation import gettext, override
from playwright.sync_api import Page, expect


def _tr(text):
    with override("ru"):
        return gettext(text)


@pytest.mark.django_db(transaction=True)
def test_a_guest_in_another_skin_switches_with_one_tap_and_is_not_asked_again(page: Page, live_server, settings):
    settings.SKIN_OFFER = "orange"
    host = live_server.url.split("//")[1].split(":")[0]
    page.context.add_cookies([{"name": "skin", "value": "dark", "domain": host, "path": "/"}])
    page.goto(f"{live_server.url}/ru/news/")
    offer = page.locator("#skin-offer")
    expect(offer).to_be_visible()
    offer.get_by_role("button", name=_tr("Switch to it")).click()
    expect(page.locator("html")).to_have_attribute("data-skin", "orange")
    expect(page.locator("#skin-offer")).to_have_count(0)
    # Back to dark by hand: tried once, so the offer stays away.
    page.context.add_cookies([{"name": "skin", "value": "dark", "domain": host, "path": "/"}])
    page.goto(f"{live_server.url}/ru/news/")
    expect(page.locator("html")).to_have_attribute("data-skin", "dark")
    expect(page.locator("#skin-offer")).to_have_count(0)
