"""A member reaches their profile from the menu, right before Search: folded on a phone, in the row on
a desktop. The account menu at the right holds it too.
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
def test_on_a_desktop_the_menu_row_opens_the_profile(page: Page, live_server, member):
    name, path = _in_russian(pgettext, *PAGE), _in_russian(reverse, "account_profile")
    inject_session(page, live_server, member)
    page.set_viewport_size(DESKTOP)
    page.goto(f"{live_server.url}/ru/calendar/")
    page.locator("#mainNav .navbar-nav").get_by_role("link", name=name, exact=True).click()
    page.wait_for_url(f"{live_server.url}{path}")
    here = page.locator("#mainNav .navbar-nav").get_by_role("link", name=name, exact=True)
    expect(here).to_have_attribute("aria-current", "page")


@pytest.mark.django_db(transaction=True)
def test_on_a_desktop_the_account_menu_opens_the_profile_too(page: Page, live_server, member):
    name, path = _in_russian(pgettext, *PAGE), _in_russian(reverse, "account_profile")
    inject_session(page, live_server, member)
    page.set_viewport_size(DESKTOP)
    page.goto(f"{live_server.url}/ru/calendar/")
    # The account menu's button bears the member's address, shown or, beside icons alone, for screen readers
    page.locator("#mainNav").get_by_role("button", name=member.email).click()
    page.locator("#mainNav .dropdown-menu").get_by_role("link", name=name, exact=True).click()
    page.wait_for_url(f"{live_server.url}{path}")
