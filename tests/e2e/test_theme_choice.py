"""The skin a reader picks from the list in the navbar: kept in a member's profile, in a guest's cookie."""

import re

import pytest
from django.conf import settings
from playwright.sync_api import Page, expect

from accounts.models import User
from cycling_site.skins import registry
from tests.e2e.conftest import inject_session, open_navbar_if_collapsed

# The icon shows the mode the page is in: a sun in light, a moon in dark.
ICON = {"light": "\u2600", "dark": "\u263e"}


def _start():
    """The skin a new member or a first-time guest is in: the one the suite runs in (E2E_SKIN)."""
    return registry()[settings.DEFAULT_SKIN]


def _other():
    """A skin of the other mode than the starting one, so that picking it shows."""
    return "light" if _start().mode == "dark" else "dark"


def pick(page: Page, where: str, key: str) -> None:
    """Open the chooser in the navbar or on the page and pick a skin from it."""
    chooser = page.locator(f"{where} .skin-select")
    chooser.locator("> button").click()
    chooser.locator(f"[data-skin-key='{key}']").click()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("language", ["ru", "kk", "en"])
def test_a_signed_in_choice_is_saved_and_kept_on_the_next_page(page: Page, live_server, language):
    member = User.objects.create_user(
        username="e2e_themer", email="e2e_themer@test.local", password="testpass123!", role=User.Role.PARTICIPANT
    )
    inject_session(page, live_server, member)
    page.goto(f"{live_server.url}/{language}/news/")
    open_navbar_if_collapsed(page)

    other = _other()
    with page.expect_response(lambda r: r.request.method == "POST" and "/accounts/theme/" in r.url) as saved:
        pick(page, "nav", other)
    assert saved.value.status == 200, saved.value.url
    member.refresh_from_db()
    assert member.theme == other

    page.goto(f"{live_server.url}/{language}/calendar/list/")
    expect(page.locator("html")).to_have_attribute("data-bs-theme", other)


def _skin_cookie(page):
    return next((c["value"] for c in page.context.cookies() if c["name"] == "skin"), None)


@pytest.mark.django_db(transaction=True)
def test_a_guests_old_choice_in_the_browser_is_carried_over_to_the_cookie(page: Page, live_server):
    page.add_init_script("localStorage.setItem('theme', 'dark')")
    page.goto(f"{live_server.url}/ru/news/")
    expect(page.locator("html")).to_have_attribute("data-bs-theme", "dark")
    expect(page.locator("html")).to_have_attribute("data-skin", "dark")
    assert _skin_cookie(page) == "dark"
    # The chooser was drawn for light; on this very page it already shows dark.
    chooser = page.locator("nav .skin-select")
    expect(chooser.locator(".skin-icon")).to_have_text(ICON["dark"])
    expect(chooser.locator("[data-skin-key='dark']")).to_have_class(re.compile(r"\bactive\b"))
    expect(chooser.locator("[data-skin-key='light']")).not_to_have_class(re.compile(r"\bactive\b"))

    # From now on the server draws it: the carrying-over script is no longer on the page.
    page.goto(f"{live_server.url}/ru/calendar/list/")
    expect(page.locator("html")).to_have_attribute("data-skin", "dark")
    expect(page.locator("#skin-modes")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_an_old_value_no_skin_answers_to_is_ignored(page: Page, live_server):
    page.add_init_script("localStorage.setItem('theme', 'retired-skin')")
    page.goto(f"{live_server.url}/ru/news/")
    expect(page.locator("html")).to_have_attribute("data-skin", _start().key)
    expect(page.locator("html")).to_have_attribute("data-bs-theme", _start().mode)
    assert _skin_cookie(page) is None


@pytest.mark.django_db(transaction=True)
def test_a_guests_choice_is_kept_on_the_next_page(page: Page, live_server):
    page.goto(f"{live_server.url}/ru/news/")
    open_navbar_if_collapsed(page)
    other = _other()
    pick(page, "nav", other)
    assert _skin_cookie(page) == other
    page.goto(f"{live_server.url}/ru/calendar/list/")
    expect(page.locator("html")).to_have_attribute("data-skin", other)


@pytest.mark.django_db(transaction=True)
def test_the_list_opens_from_the_old_switch_and_agrees_with_the_profile(page: Page, live_server):
    member = User.objects.create_user(
        username="e2e_themer", email="e2e_themer@test.local", password="testpass123!", role=User.Role.PARTICIPANT
    )
    inject_session(page, live_server, member)
    page.goto(f"{live_server.url}/ru/accounts/profile/")
    open_navbar_if_collapsed(page)
    navbar = page.locator("nav .skin-select")
    # The same moon button as the switch, in the row of the language buttons; on a phone in the menu.
    expect(navbar.locator(".skin-icon")).to_have_text(ICON[_start().mode])
    language = page.locator("nav form:has(input[name='language']) button").first
    lb, sb = language.bounding_box(), navbar.locator("> button").bounding_box()
    assert lb is not None and sb is not None
    assert abs((lb["y"] + lb["height"] / 2) - (sb["y"] + sb["height"] / 2)) < 4, (lb, sb)
    navbar.locator("> button").click()
    expect(navbar.locator("[data-skin-key]")).to_have_text([skin.names["ru"] for skin in registry().values()])
    navbar.locator("> button").click()

    other = registry()[_other()]
    pick(page, "main", other.key)
    expect(page.locator("html")).to_have_attribute("data-bs-theme", other.mode)
    expect(page.locator("main .skin-select .skin-name")).to_have_text(other.names["ru"])
    expect(navbar.locator(".skin-icon")).to_have_text(ICON[other.mode])
    expect(navbar.locator(f"[data-skin-key='{other.key}']")).to_have_class(re.compile(r"\bactive\b"))


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("where", ["nav", "main"])
def test_the_open_list_stays_on_the_screen(page: Page, live_server, where):
    member = User.objects.create_user(
        username="e2e_themer", email="e2e_themer@test.local", password="testpass123!", role=User.Role.PARTICIPANT
    )
    inject_session(page, live_server, member)
    page.goto(f"{live_server.url}/ru/accounts/profile/")
    open_navbar_if_collapsed(page)
    chooser = page.locator(f"{where} .skin-select")
    chooser.locator("> button").click()
    menu = chooser.locator(".dropdown-menu")
    expect(menu).to_be_visible()
    box = menu.bounding_box()
    assert box is not None
    width = page.evaluate("document.documentElement.clientWidth")
    assert box["x"] >= 0 and box["x"] + box["width"] <= width, (box, width)
