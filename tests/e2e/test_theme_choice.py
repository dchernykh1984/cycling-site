"""The colour theme a signed-in reader picks is kept in their profile, in every language."""

import pytest
from playwright.sync_api import Page, expect

from accounts.models import User
from tests.e2e.conftest import inject_session, open_navbar_if_collapsed


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
        page.locator("nav button[onclick='toggleTheme()']").click()
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
    page.locator("nav button[onclick='toggleTheme()']").click()
    assert _skin_cookie(page) == "dark"
    page.goto(f"{live_server.url}/ru/calendar/list/")
    expect(page.locator("html")).to_have_attribute("data-skin", "dark")
