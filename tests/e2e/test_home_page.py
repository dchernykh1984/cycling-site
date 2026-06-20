"""E2E tests for the home page and its edit form."""

import pytest
from playwright.sync_api import Page, expect

from home.models import SiteContent
from tests.e2e.conftest import inject_session, switch_locale


@pytest.fixture
def site_content(db):
    obj, _ = SiteContent.objects.update_or_create(
        pk=1,
        defaults={
            "navbar_title_ru": "TestNavbar",
            "navbar_title_en": "Cycling",
            "page_title_ru": "TestTitle",
            "body_ru": "<p>Site content</p>",
        },
    )
    return obj


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
# Home page (anonymous / any user)
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_home_page_shows_edit_button_for_owner(page: Page, live_server, owner, site_content):
    inject_session(page, live_server, owner)
    page.goto(f"{live_server.url}/")
    expect(page.locator("a[href*='home/edit']")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_home_page_no_edit_button_for_anonymous(page: Page, live_server, site_content):
    page.goto(f"{live_server.url}/")
    expect(page.locator("a[href*='home/edit']")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_home_page_no_edit_button_for_organizer(page: Page, live_server, organizer, site_content):
    inject_session(page, live_server, organizer)
    page.goto(f"{live_server.url}/")
    expect(page.locator("a[href*='home/edit']")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_home_page_shows_body_content(page: Page, live_server, site_content):
    page.goto(f"{live_server.url}/")
    expect(page.locator("body")).to_contain_text("Site content")


@pytest.mark.django_db(transaction=True)
def test_navbar_shows_navbar_title(page: Page, live_server, site_content):
    page.goto(f"{live_server.url}/")
    expect(page.locator(".navbar-brand")).to_contain_text("TestNavbar")


# ---------------------------------------------------------------------------
# Edit form - access control
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_edit_page_redirects_anonymous_to_login(page: Page, live_server, site_content):
    page.goto(f"{live_server.url}/home/edit/")
    assert "login" in page.url or "/home/edit/" not in page.url


@pytest.mark.django_db(transaction=True)
def test_edit_page_returns_403_for_organizer(page: Page, live_server, organizer, site_content):
    inject_session(page, live_server, organizer)
    response = page.goto(f"{live_server.url}/home/edit/")
    assert response is not None and response.status == 403


@pytest.mark.django_db(transaction=True)
def test_edit_page_accessible_by_owner(page: Page, live_server, owner, site_content):
    inject_session(page, live_server, owner)
    page.goto(f"{live_server.url}/home/edit/")
    expect(page.locator("#localeTabs")).to_be_visible()
    expect(page.locator("#pane-ru")).to_be_visible()


# ---------------------------------------------------------------------------
# Edit form - locale tabs
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_edit_form_has_three_locale_tabs(page: Page, live_server, owner, site_content):
    inject_session(page, live_server, owner)
    page.goto(f"{live_server.url}/home/edit/")
    expect(page.locator("#tab-ru")).to_be_visible()
    expect(page.locator("#tab-kk")).to_be_visible()
    expect(page.locator("#tab-en")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_kk_tab_shows_fields_when_clicked(page: Page, live_server, owner, site_content):
    inject_session(page, live_server, owner)
    page.goto(f"{live_server.url}/home/edit/")
    page.click("#tab-kk")
    expect(page.locator("#pane-kk")).to_be_visible()
    expect(page.locator("#pane-kk input[name='navbar_title_kk']")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_en_tab_shows_fields_when_clicked(page: Page, live_server, owner, site_content):
    inject_session(page, live_server, owner)
    page.goto(f"{live_server.url}/home/edit/")
    page.click("#tab-en")
    expect(page.locator("#pane-en")).to_be_visible()
    expect(page.locator("#pane-en input[name='navbar_title_en']")).to_be_visible()


# ---------------------------------------------------------------------------
# Edit form - save and reflect
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_edit_form_saves_navbar_title_and_reflects_in_navbar(page: Page, live_server, owner, site_content):
    """Saving a new navbar title via the form updates the navbar on the home page."""
    inject_session(page, live_server, owner)
    page.goto(f"{live_server.url}/home/edit/")

    page.fill("#id_navbar_title_ru", "My Cycling")
    page.locator("#home-edit-form button[type=submit]").click()

    expect(page.locator(".navbar-brand")).to_contain_text("My Cycling")


@pytest.mark.django_db(transaction=True)
def test_edit_form_saves_all_locale_navbar_titles_and_reflect(page: Page, live_server, owner, site_content):
    """Owner fills navbar titles for all three locale tabs; each locale reflects correctly."""
    inject_session(page, live_server, owner)
    page.goto(f"{live_server.url}/home/edit/")

    page.fill("#id_navbar_title_ru", "TitleRU")

    page.click("#tab-kk")
    page.fill("#id_navbar_title_kk", "TitleKK")

    page.click("#tab-en")
    page.fill("#id_navbar_title_en", "TitleEN")

    page.locator("#home-edit-form button[type=submit]").click()

    expect(page.locator(".navbar-brand")).to_contain_text("TitleRU")

    switch_locale(page, "kk")
    expect(page.locator(".navbar-brand")).to_contain_text("TitleKK")

    switch_locale(page, "en")
    expect(page.locator(".navbar-brand")).to_contain_text("TitleEN")


@pytest.mark.django_db(transaction=True)
def test_edit_form_saves_body_via_editor(page: Page, live_server, owner, site_content):
    """Editing the RU body through the shared Quill editor saves and renders on the home page."""
    inject_session(page, live_server, owner)
    page.goto(f"{live_server.url}/home/edit/")
    # Set the body through the shared editor DOM and submit in one synchronous step (deterministic
    # across engines; see tests/e2e/test_knowledge_editor.py for the rationale).
    page.evaluate(
        """() => {
          document.querySelector('#quill-ru .ql-editor').innerHTML = '<p>Home body via editor</p>';
          document.getElementById('home-edit-form').requestSubmit();
        }"""
    )
    page.wait_for_load_state("networkidle")

    page.goto(f"{live_server.url}/")
    expect(page.locator(".home-body")).to_contain_text("Home body via editor")


# ---------------------------------------------------------------------------
# Per-locale content display
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_home_navbar_shows_correct_title_per_locale(page: Page, live_server, site_content_multilingual):
    """Navbar title is locale-specific: RU, KK, EN each show their own value."""
    page.goto(f"{live_server.url}/")
    expect(page.locator(".navbar-brand")).to_contain_text("NavRU")

    switch_locale(page, "kk")
    expect(page.locator(".navbar-brand")).to_contain_text("NavKK")

    switch_locale(page, "en")
    expect(page.locator(".navbar-brand")).to_contain_text("NavEN")


@pytest.mark.django_db(transaction=True)
def test_home_body_shows_correct_content_per_locale(page: Page, live_server, site_content_multilingual):
    """Home page body renders locale-specific content for anonymous visitors."""
    page.goto(f"{live_server.url}/")
    expect(page.locator("body")).to_contain_text("BodyRU")

    switch_locale(page, "kk")
    expect(page.locator("body")).to_contain_text("BodyKK")

    switch_locale(page, "en")
    expect(page.locator("body")).to_contain_text("BodyEN")


# ---------------------------------------------------------------------------
# Edit button visibility by role across all locales
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_owner_sees_edit_button_in_kk_and_en_locales(page: Page, live_server, owner, site_content_multilingual):
    """Owner sees the edit button in KK and EN locales, not only the default locale."""
    inject_session(page, live_server, owner)
    page.goto(f"{live_server.url}/")

    switch_locale(page, "kk")
    expect(page.locator("a[href*='home/edit']")).to_be_visible()

    switch_locale(page, "en")
    expect(page.locator("a[href*='home/edit']")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_no_edit_button_for_organizer_in_kk_and_en_locales(
    page: Page, live_server, organizer, site_content_multilingual
):
    """Organizer sees no edit button in KK and EN locales."""
    inject_session(page, live_server, organizer)
    page.goto(f"{live_server.url}/")

    switch_locale(page, "kk")
    expect(page.locator("a[href*='home/edit']")).to_have_count(0)

    switch_locale(page, "en")
    expect(page.locator("a[href*='home/edit']")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_no_edit_button_for_anonymous_in_kk_and_en_locales(page: Page, live_server, site_content_multilingual):
    """Anonymous user sees no edit button in KK and EN locales."""
    page.goto(f"{live_server.url}/")

    switch_locale(page, "kk")
    expect(page.locator("a[href*='home/edit']")).to_have_count(0)

    switch_locale(page, "en")
    expect(page.locator("a[href*='home/edit']")).to_have_count(0)
