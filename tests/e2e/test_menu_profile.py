"""A member reaches their profile from the menu.

On a phone the folded menu ends with it. A desktop row has no room for one more link -- measured, it
made the header a row taller in every skin, in Russian at 1400px and wider -- so there the account menu
at the right holds it.
"""

import pytest
from django.urls import reverse
from django.utils import translation
from django.utils.translation import pgettext
from playwright.sync_api import Page, ViewportSize, expect

from accounts.models import User
from tests.e2e.conftest import inject_session, open_navbar_if_collapsed
from tests.test_profile_name import PAGE

PHONE: ViewportSize = {"width": 360, "height": 740}
DESKTOP: ViewportSize = {"width": 1280, "height": 800}


def _in_russian(callable_, *args):
    with translation.override("ru"):
        return callable_(*args)


@pytest.fixture
def member(db):
    return User.objects.create_user(username="member", email="member@example.com", password="Strong-pass-2026")


@pytest.mark.django_db(transaction=True)
def test_on_a_phone_the_folded_menu_opens_the_profile(page: Page, live_server, member):
    name, path = _in_russian(pgettext, *PAGE), _in_russian(reverse, "account_profile")
    inject_session(page, live_server, member)
    page.set_viewport_size(PHONE)
    page.goto(f"{live_server.url}/ru/calendar/")
    open_navbar_if_collapsed(page)
    page.locator("#mainNav .navbar-nav").get_by_role("link", name=name, exact=True).click()
    # Until the page has loaded its styles the folded menu shows unfolded, and the link is marked on load
    page.wait_for_url(f"{live_server.url}{path}")
    expect(page.get_by_role("heading", level=1)).to_have_text(name)
    open_navbar_if_collapsed(page)
    here = page.locator("#mainNav .navbar-nav").get_by_role("link", name=name, exact=True)
    expect(here).to_have_attribute("aria-current", "page")


@pytest.mark.django_db(transaction=True)
def test_a_desktop_finds_the_profile_in_the_account_menu(page: Page, live_server, member):
    name, path = _in_russian(pgettext, *PAGE), _in_russian(reverse, "account_profile")
    inject_session(page, live_server, member)
    page.set_viewport_size(DESKTOP)
    page.goto(f"{live_server.url}/ru/calendar/")
    in_the_row = page.locator(f'#mainNav .navbar-nav a[href="{path}"]')
    expect(in_the_row).to_have_count(1)
    expect(in_the_row).to_be_hidden()
    # The account menu's button bears the member's address, shown or, beside icons alone, for screen readers
    page.locator("#mainNav").get_by_role("button", name=member.email).click()
    page.locator("#mainNav .dropdown-menu").get_by_role("link", name=name, exact=True).click()
    page.wait_for_url(f"{live_server.url}{path}")
