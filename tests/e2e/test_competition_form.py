"""E2E tests for the competition submit/edit form JS behaviour."""

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import inject_session

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _goto_submit(page: Page, live_server, user):
    inject_session(page, live_server, user)
    page.goto(f"{live_server.url}/calendar/submit/")


# ---------------------------------------------------------------------------
# registration section toggle
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_registration_section_hidden_by_default(page: Page, live_server, organizer):
    _goto_submit(page, live_server, organizer)
    expect(page.locator("#reg-collapse")).not_to_have_class(re.compile(r"\bshow\b"))


@pytest.mark.django_db(transaction=True)
def test_registration_section_expands_on_check(page: Page, live_server, organizer):
    _goto_submit(page, live_server, organizer)
    page.locator("#reg_enabled").check()
    expect(page.locator("#reg-collapse")).to_have_class(re.compile(r"\bshow\b"))


# ---------------------------------------------------------------------------
# url_registration field visibility
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_url_registration_visible_by_default(page: Page, live_server, organizer):
    _goto_submit(page, live_server, organizer)
    expect(page.locator("#id_url_registration")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_url_registration_hidden_when_registration_enabled(page: Page, live_server, organizer):
    _goto_submit(page, live_server, organizer)
    page.locator("#reg_enabled").check()
    expect(page.locator("#id_url_registration").locator("..")).to_have_css("display", "none")


@pytest.mark.django_db(transaction=True)
def test_url_registration_reappears_when_registration_disabled(page: Page, live_server, organizer):
    _goto_submit(page, live_server, organizer)
    page.locator("#reg_enabled").check()
    page.locator("#reg_enabled").uncheck()
    expect(page.locator("#id_url_registration")).to_be_visible()


# ---------------------------------------------------------------------------
# allow multiple registrations visibility
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_allow_multiple_hidden_in_self_only_mode(page: Page, live_server, organizer):
    _goto_submit(page, live_server, organizer)
    page.locator("#reg_enabled").check()
    # Default mode is self_only - allow_multi_wrap must be hidden
    expect(page.locator("#allow_multi_wrap")).to_have_css("display", "none")


@pytest.mark.django_db(transaction=True)
def test_allow_multiple_visible_in_free_mode(page: Page, live_server, organizer):
    _goto_submit(page, live_server, organizer)
    page.locator("#reg_enabled").check()
    page.locator("#mode_free").check()
    expect(page.locator("#allow_multi_wrap")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_allow_multiple_hides_again_when_switching_back_to_self_only(page: Page, live_server, organizer):
    _goto_submit(page, live_server, organizer)
    page.locator("#reg_enabled").check()
    page.locator("#mode_free").check()
    page.locator("#mode_self").check()
    expect(page.locator("#allow_multi_wrap")).to_have_css("display", "none")
    # Checkbox should be unchecked
    expect(page.locator("#allow_multi")).not_to_be_checked()


# ---------------------------------------------------------------------------
# display settings gated on require_approval / require_payment
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_display_settings_hidden_without_approval_and_payment(page: Page, live_server, organizer):
    _goto_submit(page, live_server, organizer)
    page.locator("#reg_enabled").check()
    # Both checkboxes unchecked by default - section invisible
    expect(page.locator("#req_approval")).not_to_be_checked()
    expect(page.locator("#req_payment")).not_to_be_checked()
    expect(page.locator("#display-settings-section")).to_have_css("display", "none")


@pytest.mark.django_db(transaction=True)
def test_display_settings_visible_when_approval_enabled(page: Page, live_server, organizer):
    _goto_submit(page, live_server, organizer)
    page.locator("#reg_enabled").check()
    page.locator("#req_approval").check()
    expect(page.locator("#display-settings-section")).to_be_visible()
    expect(page.locator("#show_unappr_wrap")).to_be_visible()
    expect(page.locator("#show_appr_col_wrap")).to_be_visible()
    expect(page.locator("#show_unpaid_wrap")).to_have_css("display", "none")
    expect(page.locator("#show_paid_col_wrap")).to_have_css("display", "none")


@pytest.mark.django_db(transaction=True)
def test_display_settings_visible_when_payment_enabled(page: Page, live_server, organizer):
    _goto_submit(page, live_server, organizer)
    page.locator("#reg_enabled").check()
    page.locator("#req_payment").check()
    expect(page.locator("#display-settings-section")).to_be_visible()
    expect(page.locator("#show_unpaid_wrap")).to_be_visible()
    expect(page.locator("#show_paid_col_wrap")).to_be_visible()
    expect(page.locator("#show_unappr_wrap")).to_have_css("display", "none")
    expect(page.locator("#show_appr_col_wrap")).to_have_css("display", "none")


@pytest.mark.django_db(transaction=True)
def test_display_checkboxes_unchecked_when_parent_disabled(page: Page, live_server, organizer):
    """Checkboxes that were checked must be cleared when their parent is unchecked."""
    _goto_submit(page, live_server, organizer)
    page.locator("#reg_enabled").check()
    page.locator("#req_approval").check()
    page.locator("#show_unappr").check()
    page.locator("#show_appr_col").check()
    # Now disable require_approval.
    # Scroll to center first: default scrollIntoView puts the element at the top of the
    # viewport, where the sticky navbar intercepts the click on narrow mobile screens.
    page.locator("#req_approval").evaluate("el => el.scrollIntoView({block: 'center', behavior: 'instant'})")
    page.locator("#req_approval").uncheck()
    expect(page.locator("#show_unappr")).not_to_be_checked()
    expect(page.locator("#show_appr_col")).not_to_be_checked()


# ---------------------------------------------------------------------------
# category rows layout (two-line rendering)
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_category_row_has_two_lines(page: Page, live_server, organizer):
    _goto_submit(page, live_server, organizer)
    page.locator("#reg_enabled").check()
    page.locator("#add-category-btn").click()
    # First row contains name input
    first_row = page.locator("#categories-container .card").first
    expect(first_row.locator(".row").first.locator("input[placeholder]").first).to_be_visible()
    # Second row contains Laps input
    expect(first_row.locator(".row").nth(1).locator("input[placeholder]").first).to_be_visible()
