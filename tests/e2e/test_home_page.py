"""E2E tests for the home page and its edit form."""

import pytest
from playwright.sync_api import Page, expect

from home.models import SiteContent
from tests.e2e.conftest import inject_session


@pytest.fixture
def site_content(db):
    obj, _ = SiteContent.objects.get_or_create(
        pk=1,
        defaults={
            "navbar_title_ru": "TestNavbar",
            "navbar_title_en": "Cycling",
            "page_title_ru": "TestTitle",
            "body_ru": "<p>Site content</p>",
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
    page.click("button[type=submit]")
    page.wait_for_url(f"{live_server.url}/")

    expect(page.locator(".navbar-brand")).to_contain_text("My Cycling")
