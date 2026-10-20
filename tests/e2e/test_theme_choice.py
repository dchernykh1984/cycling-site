"""The skin a reader picks from the list in the navbar: kept in a member's profile, in a guest's cookie."""

import re

import pytest
from playwright.sync_api import Page, expect

from accounts.models import User
from tests.e2e.conftest import inject_session, open_navbar_if_collapsed


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

    with page.expect_response(lambda r: r.request.method == "POST" and "/accounts/theme/" in r.url) as saved:
        pick(page, "nav", "dark")
    assert saved.value.status == 200, saved.value.url
    member.refresh_from_db()
    assert member.theme == "dark"

    page.goto(f"{live_server.url}/{language}/calendar/list/")
    expect(page.locator("html")).to_have_attribute("data-bs-theme", "dark")


def _skin_cookie(page):
    return next((c["value"] for c in page.context.cookies() if c["name"] == "skin"), None)


@pytest.mark.django_db(transaction=True)
def test_a_guests_old_choice_in_the_browser_is_carried_over_to_the_cookie(page: Page, live_server):
    page.add_init_script("localStorage.setItem('theme', 'dark')")
    page.goto(f"{live_server.url}/ru/news/")
    expect(page.locator("html")).to_have_attribute("data-bs-theme", "dark")
    expect(page.locator("html")).to_have_attribute("data-skin", "dark")
    assert _skin_cookie(page) == "dark"

    # From now on the server draws it: the carrying-over script is no longer on the page.
    page.goto(f"{live_server.url}/ru/calendar/list/")
    expect(page.locator("html")).to_have_attribute("data-skin", "dark")
    expect(page.locator("#skin-modes")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_an_old_value_no_skin_answers_to_is_ignored(page: Page, live_server):
    page.add_init_script("localStorage.setItem('theme', 'retired-skin')")
    page.goto(f"{live_server.url}/ru/news/")
    expect(page.locator("html")).to_have_attribute("data-skin", "light")
    expect(page.locator("html")).to_have_attribute("data-bs-theme", "light")
    assert _skin_cookie(page) is None


@pytest.mark.django_db(transaction=True)
def test_a_guests_choice_is_kept_on_the_next_page(page: Page, live_server):
    page.goto(f"{live_server.url}/ru/news/")
    open_navbar_if_collapsed(page)
    pick(page, "nav", "dark")
    assert _skin_cookie(page) == "dark"
    page.goto(f"{live_server.url}/ru/calendar/list/")
    expect(page.locator("html")).to_have_attribute("data-skin", "dark")


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
    expect(navbar.locator(".skin-icon")).to_have_text("\u263e")
    language = page.locator("nav form:has(input[name='language']) button").first
    lb, sb = language.bounding_box(), navbar.locator("> button").bounding_box()
    assert lb is not None and sb is not None
    assert abs((lb["y"] + lb["height"] / 2) - (sb["y"] + sb["height"] / 2)) < 4, (lb, sb)
    navbar.locator("> button").click()
    expect(navbar.locator("[data-skin-key]")).to_have_text(
        ["\u0421\u0432\u0435\u0442\u043b\u0430\u044f", "\u0422\u0451\u043c\u043d\u0430\u044f"]
    )
    navbar.locator("> button").click()

    pick(page, "main", "dark")
    expect(page.locator("html")).to_have_attribute("data-bs-theme", "dark")
    expect(page.locator("main .skin-select .skin-name")).to_have_text("\u0422\u0451\u043c\u043d\u0430\u044f")
    expect(navbar.locator(".skin-icon")).to_have_text("\u2600")
    expect(navbar.locator("[data-skin-key='dark']")).to_have_class(re.compile(r"\bactive\b"))
