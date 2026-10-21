"""A skin with a stylesheet, a script and templates of its own, as a reader picks it."""

import pytest
from playwright.sync_api import Page, expect

from accounts.models import User
from tests.e2e.conftest import inject_session, open_navbar_if_collapsed
from tests.skin_fixtures import trial_skin

OWN = {
    "css": ':root[data-skin="trial"] body { outline: 3px solid rgb(1, 2, 3); }',
    "script": "document.documentElement.dataset.trialScript = 'ran';",
    "templates": {"_share_button.html": '<span class="trial-share">trial</span>'},
}


def _pick(page: Page, key: str):
    open_navbar_if_collapsed(page)
    chooser = page.locator("nav .skin-select")
    chooser.locator("> button").click()
    # Into a skin of its own, or out of it: the page reloads to bring its parts in or take them away.
    with page.expect_navigation():
        chooser.locator(f"[data-skin-key='{key}']").click()


def _pick_trial(page: Page):
    _pick(page, "trial")


def _in_trial(page: Page):
    expect(page.locator("html")).to_have_attribute("data-skin", "trial")
    expect(page.locator("html")).to_have_attribute("data-bs-theme", "dark")
    expect(page.locator("html")).to_have_attribute("data-trial-script", "ran")
    expect(page.locator("body")).to_have_css("outline-color", "rgb(1, 2, 3)")
    expect(page.locator(".trial-share")).to_be_visible()
    expect(page.locator(".share-btn")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_a_guest_picks_it_and_the_page_comes_back_in_it(page: Page, live_server, tmp_path):
    with trial_skin(tmp_path, **OWN):
        page.goto(f"{live_server.url}/ru/news/")
        expect(page.locator(".trial-share")).to_have_count(0)
        _pick_trial(page)
        _in_trial(page)


@pytest.mark.django_db(transaction=True)
def test_a_member_picks_it_and_keeps_it(page: Page, live_server, tmp_path):
    member = User.objects.create_user(
        username="e2e_trial", email="e2e_trial@test.local", password="testpass123!", role=User.Role.PARTICIPANT
    )
    with trial_skin(tmp_path, **OWN):
        inject_session(page, live_server, member)
        page.goto(f"{live_server.url}/ru/news/")
        _pick_trial(page)
        _in_trial(page)
        member.refresh_from_db()
        assert member.theme == "trial"
        page.goto(f"{live_server.url}/ru/calendar/list/")
        expect(page.locator("html")).to_have_attribute("data-skin", "trial")


def _out_of_trial(page: Page, base: str):
    expect(page.locator("html")).to_have_attribute("data-skin", base)
    expect(page.locator("html")).to_have_attribute("data-bs-theme", base)
    expect(page.locator("html")).not_to_have_attribute("data-trial-script", "ran")
    expect(page.locator(".trial-share")).to_have_count(0)
    expect(page.locator(".share-btn")).to_be_visible()
    expect(page.locator("link[href*='skins/trial/']")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("base", ["light", "dark"])
def test_a_guest_leaving_it_gets_the_page_back_without_any_of_it(page: Page, live_server, tmp_path, base):
    with trial_skin(tmp_path, **OWN):
        page.goto(f"{live_server.url}/ru/news/")
        _pick_trial(page)
        _in_trial(page)
        _pick(page, base)
        _out_of_trial(page, base)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("base", ["light", "dark"])
def test_a_member_leaving_it_gets_the_page_back_without_any_of_it(page: Page, live_server, tmp_path, base):
    member = User.objects.create_user(
        username="e2e_trial", email="e2e_trial@test.local", password="testpass123!", role=User.Role.PARTICIPANT
    )
    with trial_skin(tmp_path, **OWN):
        inject_session(page, live_server, member)
        page.goto(f"{live_server.url}/ru/news/")
        _pick_trial(page)
        _pick(page, base)
        _out_of_trial(page, base)
        member.refresh_from_db()
        assert member.theme == base
