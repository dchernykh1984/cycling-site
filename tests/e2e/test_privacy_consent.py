"""E2E for the privacy question at the first sign-in of an account a provider made (issue #438): the
page asks before any other and goes on to the page asked for, and its one box can be seen."""

import pytest
from playwright.sync_api import Page, expect

from accounts.models import User
from tests.e2e.conftest import inject_session
from tests.e2e.contrast import drawn, ratio

# How far the link stands from the words beside it on the same line, in pixels: about a space when the
# space is drawn, nothing when a row layout swallowed it. The words come before the link in Russian
# and English, after it in Kazakh; on another line there is nothing to measure.
SPACE_BESIDE_THE_LINK = """(label) => {
  const link = label.querySelector('a'), lines = link.getClientRects(), range = document.createRange();
  const before = link.previousSibling, after = link.nextSibling;
  if (before && before.textContent.trim()) {
    range.setStart(before, 0);
    range.setEnd(before, before.textContent.replace(/\\s+$/, '').length);
    const words = range.getClientRects(), last = words[words.length - 1], start = lines[0];
    return Math.abs(last.top - start.top) > 2 ? 99 : start.left - last.right;
  }
  const lead = after.textContent.length - after.textContent.replace(/^\\s+/, '').length;
  range.setStart(after, lead);
  range.setEnd(after, after.textContent.length);
  const first = range.getClientRects()[0], end = lines[lines.length - 1];
  return Math.abs(first.top - end.top) > 2 ? 99 : first.left - end.right;
}"""


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
    words = page.locator(".privacy-consent-pick")
    words_at = words.bounding_box()
    assert words_at and round(words_at["height"], 1) >= 44
    assert words.evaluate(SPACE_BESIDE_THE_LINK) >= 2


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("lang", ["ru", "kk", "en"])
def test_on_the_sign_up_form_the_box_comes_first_takes_a_tap_and_can_be_seen(page: Page, live_server, lang):
    page.set_viewport_size({"width": 360, "height": 800})
    page.goto(f"{live_server.url}/{lang}/accounts/signup/")
    box, words = page.locator("#id_privacy"), page.locator('label[for="id_privacy"]')
    box_at, words_at = box.bounding_box(), words.bounding_box()
    assert box_at and words_at
    assert box_at["x"] < words_at["x"]
    assert words.evaluate(SPACE_BESIDE_THE_LINK) >= 2
    assert round(words_at["height"], 1) >= 44
    assert page.evaluate("document.scrollingElement.scrollWidth <= document.scrollingElement.clientWidth")
    frame = drawn(box, "colour:" + box.evaluate("el => getComputedStyle(el).borderTopColor"))
    assert ratio(frame, drawn(box, "fill-beneath")) >= 3
