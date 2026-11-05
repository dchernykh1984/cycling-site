"""E2E for the privacy question at the first sign-in of an account a provider made (issue #438): the
page asks before any other and goes on to the page asked for, and its one box can be seen."""

import pytest
from playwright.sync_api import Page, expect

from accounts.models import User
from tests.e2e.conftest import inject_session
from tests.e2e.contrast import drawn, ratio


@pytest.fixture
def newcomer(db):
    user = User.objects.create_user(
        username="newcomer", email="newcomer@test.local", password="testpass123!", role=User.Role.PARTICIPANT
    )
    user.privacy_consent_pending = True
    user.save(update_fields=["privacy_consent_pending"])
    return user


@pytest.mark.django_db(transaction=True)
def test_the_question_comes_first_and_the_page_asked_for_after_the_yes(page: Page, live_server, newcomer):
    inject_session(page, live_server, newcomer)
    page.goto(f"{live_server.url}/en/calendar/list/")
    expect(page).to_have_url(f"{live_server.url}/en/accounts/privacy-consent/?next=%2Fen%2Fcalendar%2Flist%2F")
    policy = page.locator(".privacy-consent").get_by_role("link", name="privacy policy")
    expect(policy).to_have_attribute("target", "_blank")
    page.get_by_label("I agree with the privacy policy").check()
    page.get_by_role("button", name="Continue").click()
    expect(page).to_have_url(f"{live_server.url}/en/calendar/list/")
    newcomer.refresh_from_db()
    assert newcomer.privacy_accepted_at is not None and not newcomer.privacy_consent_pending


@pytest.mark.django_db(transaction=True)
def test_the_box_can_be_seen_in_this_skin(page: Page, live_server, newcomer):
    """An empty box is all the page asks for: its frame stands 3:1 against what it is drawn on."""
    inject_session(page, live_server, newcomer)
    page.goto(f"{live_server.url}/en/accounts/privacy-consent/")
    box = page.locator(".privacy-consent .form-check-input")
    frame = drawn(box, "colour:" + box.evaluate("el => getComputedStyle(el).borderTopColor"))
    assert ratio(frame, drawn(box, "fill-beneath")) >= 3
