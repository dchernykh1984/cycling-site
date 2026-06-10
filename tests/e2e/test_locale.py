"""E2E tests for unified cookie-based locale switching across pages.

All locale switching uses a single mechanism: the set_language form in the
navbar POST to /i18n/set_language/, which sets the django_language cookie and
(for authenticated users) saves preferred_language to the User model.
"""

import pytest
from playwright.sync_api import Page, expect

from home.models import SiteContent
from tests.e2e.conftest import inject_session, open_navbar_if_collapsed, switch_locale


@pytest.fixture
def site_content_multilingual(db):
    """SiteContent with distinct navbar title and body for each of the three locales."""
    obj, _ = SiteContent.objects.update_or_create(
        pk=1,
        defaults={
            "navbar_title_ru": "NavRU",
            "navbar_title_kk": "NavKK",
            "navbar_title_en": "NavEN",
            "body_ru": "<p>BodyRU</p>",
            "body_kk": "<p>BodyKK</p>",
            "body_en": "<p>BodyEN</p>",
        },
    )
    return obj


# ---------------------------------------------------------------------------
# Locale switcher widget presence and state
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_language_buttons_present_on_homepage(page: Page, live_server, site_content_multilingual):
    """Three locale elements are visible in the navbar: active span + two clickable forms."""
    page.goto(f"{live_server.url}/")
    open_navbar_if_collapsed(page)
    # One active (non-clickable) span for the current language
    expect(page.locator("span.btn.btn-secondary.pe-none")).to_be_visible()
    # Two form submit buttons for the other two languages
    expect(page.locator("form:has(input[name='language']) button[type='submit']")).to_have_count(2)


@pytest.mark.django_db(transaction=True)
def test_active_locale_is_shown_as_span_not_button(page: Page, live_server, site_content_multilingual):
    """Default locale (RU) is rendered as a non-clickable span, not inside a form."""
    page.goto(f"{live_server.url}/")
    open_navbar_if_collapsed(page)
    # RU is the default language; it should be a span chip
    active_span = page.locator("span.btn.pe-none")
    expect(active_span).to_contain_text("RU")
    # No form for RU (can't switch to the current locale)
    expect(page.locator("form:has(input[name='language'][value='ru'])")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_language_buttons_present_on_calendar_page(page: Page, live_server, site_content_multilingual):
    """Locale switcher is present on non-Wagtail pages (calendar) too."""
    page.goto(f"{live_server.url}/calendar/")
    open_navbar_if_collapsed(page)
    expect(page.locator("span.btn.btn-secondary.pe-none")).to_be_visible()
    expect(page.locator("form:has(input[name='language']) button[type='submit']")).to_have_count(2)


# ---------------------------------------------------------------------------
# Single-page locale switching
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_switch_to_kk_updates_homepage_content(page: Page, live_server, site_content_multilingual):
    """Clicking the KK button switches the homepage to the Kazakh locale."""
    page.goto(f"{live_server.url}/")
    expect(page.locator(".navbar-brand")).to_contain_text("NavRU")

    switch_locale(page, "kk")

    expect(page.locator(".navbar-brand")).to_contain_text("NavKK")
    expect(page.locator("body")).to_contain_text("BodyKK")
    # KK is now the active locale (shown as span, not button)
    expect(page.locator("span.btn.pe-none")).to_contain_text("KZ")
    expect(page.locator("form:has(input[name='language'][value='kk'])")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_switch_to_en_updates_homepage_content(page: Page, live_server, site_content_multilingual):
    """Clicking the EN button switches the homepage to the English locale."""
    page.goto(f"{live_server.url}/")

    switch_locale(page, "en")

    expect(page.locator(".navbar-brand")).to_contain_text("NavEN")
    expect(page.locator("body")).to_contain_text("BodyEN")
    expect(page.locator("span.btn.pe-none")).to_contain_text("EN")


@pytest.mark.django_db(transaction=True)
def test_switch_kk_then_back_to_ru(page: Page, live_server, site_content_multilingual):
    """Switching to KK then back to RU returns to the Russian locale."""
    page.goto(f"{live_server.url}/")

    switch_locale(page, "kk")
    expect(page.locator(".navbar-brand")).to_contain_text("NavKK")

    switch_locale(page, "ru")
    expect(page.locator(".navbar-brand")).to_contain_text("NavRU")
    expect(page.locator("span.btn.pe-none")).to_contain_text("RU")


# ---------------------------------------------------------------------------
# Cross-page locale persistence (anonymous users)
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_kk_locale_persists_navigating_to_calendar(page: Page, live_server, site_content_multilingual):
    """Locale switched on homepage is preserved when navigating to the calendar page."""
    page.goto(f"{live_server.url}/")
    switch_locale(page, "kk")
    expect(page.locator(".navbar-brand")).to_contain_text("NavKK")

    page.goto(f"{live_server.url}/calendar/")

    expect(page.locator(".navbar-brand")).to_contain_text("NavKK")
    # KK is still active on the calendar page
    expect(page.locator("span.btn.pe-none")).to_contain_text("KZ")


@pytest.mark.django_db(transaction=True)
def test_kk_locale_persists_navigating_from_calendar_to_home(page: Page, live_server, site_content_multilingual):
    """Locale switched on the calendar page is preserved when navigating back to homepage."""
    page.goto(f"{live_server.url}/calendar/")
    switch_locale(page, "kk")
    expect(page.locator(".navbar-brand")).to_contain_text("NavKK")

    page.goto(f"{live_server.url}/")

    expect(page.locator(".navbar-brand")).to_contain_text("NavKK")


@pytest.mark.django_db(transaction=True)
def test_locale_persists_across_multiple_pages(page: Page, live_server, site_content_multilingual):
    """KK locale set on homepage persists through several page navigations."""
    page.goto(f"{live_server.url}/")
    switch_locale(page, "kk")

    for url in ["/calendar/", "/search/", "/"]:
        page.goto(f"{live_server.url}{url}")
        expect(page.locator(".navbar-brand")).to_contain_text("NavKK")
        expect(page.locator("span.btn.pe-none")).to_contain_text("KZ")


@pytest.mark.django_db(transaction=True)
def test_en_locale_persists_across_pages(page: Page, live_server, site_content_multilingual):
    """EN locale persists from homepage through calendar and back."""
    page.goto(f"{live_server.url}/")
    switch_locale(page, "en")

    page.goto(f"{live_server.url}/calendar/")
    expect(page.locator(".navbar-brand")).to_contain_text("NavEN")
    expect(page.locator("span.btn.pe-none")).to_contain_text("EN")

    page.goto(f"{live_server.url}/")
    expect(page.locator(".navbar-brand")).to_contain_text("NavEN")


# ---------------------------------------------------------------------------
# Authenticated user locale persistence
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_authenticated_user_switch_saves_preferred_language(page: Page, live_server, owner, site_content_multilingual):
    """Switching locale as an authenticated user saves preferred_language to the DB."""

    inject_session(page, live_server, owner)
    page.goto(f"{live_server.url}/")

    switch_locale(page, "kk")

    owner.refresh_from_db()
    assert owner.preferred_language == "kk"


@pytest.mark.django_db(transaction=True)
def test_authenticated_user_preferred_language_overrides_cookie(
    page: Page, live_server, owner, site_content_multilingual
):
    """After switching to KK, a new session with the default cookie=RU still shows KK
    because LocaleFallbackMiddleware applies preferred_language over the cookie."""
    inject_session(page, live_server, owner)
    page.goto(f"{live_server.url}/")
    switch_locale(page, "kk")

    # Re-inject session: inject_session sets django_language=ru cookie, but
    # preferred_language='kk' stored in DB should win via LocaleFallbackMiddleware.
    inject_session(page, live_server, owner)
    page.goto(f"{live_server.url}/")

    expect(page.locator(".navbar-brand")).to_contain_text("NavKK")
    expect(page.locator("span.btn.pe-none")).to_contain_text("KZ")


@pytest.mark.django_db(transaction=True)
def test_authenticated_user_locale_persists_across_pages(page: Page, live_server, owner, site_content_multilingual):
    """Authenticated user's KK locale persists through homepage -> calendar -> homepage."""
    inject_session(page, live_server, owner)
    page.goto(f"{live_server.url}/")
    switch_locale(page, "kk")

    page.goto(f"{live_server.url}/calendar/")
    expect(page.locator(".navbar-brand")).to_contain_text("NavKK")

    page.goto(f"{live_server.url}/")
    expect(page.locator(".navbar-brand")).to_contain_text("NavKK")
