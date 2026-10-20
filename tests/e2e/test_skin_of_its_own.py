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


def _pick_trial(page: Page):
    open_navbar_if_collapsed(page)
    chooser = page.locator("nav .skin-select")
    chooser.locator("> button").click()
    # Its stylesheet is not on the page yet, so picking it reloads the page with it.
    with page.expect_navigation():
        chooser.locator("[data-skin-key='trial']").click()


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
