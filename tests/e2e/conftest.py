import datetime
import os

import pytest
from django.test import Client

from accounts.models import User
from calendar_app.models import Competition, Discipline, DisciplineCategory
from registrations.models import CompetitionRegistration

# pytest-playwright creates an asyncio event loop for its fixtures; Django 4.1+
# raises SynchronousOnlyOperation when it detects a running loop. This env var
# is the official Django recommendation for running sync ORM alongside asyncio.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def default_language_cookie(page, live_server):
    """Force Russian locale for every e2e test via the django_language cookie.

    Without this, the browser's Accept-Language header (e.g. en-US sent by
    WebKit) activates English via LocaleMiddleware instead of the default RU.
    """
    host = live_server.url.split("//")[1].split(":")[0]
    page.context.add_cookies([{"name": "django_language", "value": "ru", "domain": host, "path": "/"}])


def inject_session(page, live_server, user):
    # django_language=ru cookie is read by LocaleMiddleware so CI browsers with
    # Accept-Language: en-US see Russian content by default.
    client = Client()
    client.force_login(user)
    session_value = client.cookies["sessionid"].value
    host = live_server.url.split("//")[1].split(":")[0]
    page.context.add_cookies(
        [
            {"name": "sessionid", "value": session_value, "domain": host, "path": "/"},
            {"name": "django_language", "value": "ru", "domain": host, "path": "/"},
        ]
    )


def open_filter_panel(page) -> None:
    """Expand the filter panel if it is collapsed (mobile layout hides it by default)."""
    panel = page.locator("#filter-panel")
    if not panel.is_visible():
        page.click("button[data-bs-target='#filter-panel']")
        panel.wait_for(state="visible")


def open_navbar_if_collapsed(page) -> None:
    """Open the hamburger menu on mobile if the navbar is collapsed."""
    nav = page.locator("#mainNav")
    if not nav.is_visible():
        page.locator(".navbar-toggler").click()
        nav.wait_for(state="visible")


def switch_locale(page, locale):
    """Switch locale by clicking the language-switcher form button in the navbar.

    All pages use a unified cookie-based locale via set_language form POSTs.
    Clicking the button sets the django_language cookie and redirects back to
    the current page with the new locale active.
    On mobile the navbar is collapsed; it is opened automatically before clicking.
    """
    open_navbar_if_collapsed(page)
    page.locator(f"form:has(input[name='language'][value='{locale}']) button[type='submit']").first.click()
    page.wait_for_load_state("networkidle")


# ---------------------------------------------------------------------------
# DB state fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def wagtail_locales(db):
    """Ensure Wagtail Locale rows exist for all supported languages.

    With transaction=True tests the DB is flushed between tests, so migration-
    created rows are gone. This fixture recreates them for every test so that
    templates using Locale.get_active() don't raise DoesNotExist / 500.
    """
    from wagtail.models import Locale

    for lang_code in ("ru", "en", "kk"):
        Locale.objects.get_or_create(language_code=lang_code)


@pytest.fixture(autouse=True)
def wagtail_home_page(db, wagtail_locales):
    from wagtail.models import Page, Site

    from home.models import HomePage

    if Page.objects.filter(depth=1).exists():
        return

    root = Page.add_root(title="Root", slug="root")
    home = root.add_child(instance=HomePage(title="Home", slug="home", live=True))
    Site.objects.get_or_create(
        hostname="localhost",
        defaults={"root_page": home, "is_default_site": True, "port": 80},
    )
    # No per-locale page copies needed: HomePage.get_context() and the get_site_content
    # template tag now use request.LANGUAGE_CODE (set by Django's LocaleMiddleware) to
    # resolve SiteContent locale fields, bypassing Wagtail's translation.override(page.locale).


# ---------------------------------------------------------------------------
# user fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def organizer(db):
    return User.objects.create_user(
        username="e2e_organizer",
        email="e2e_organizer@test.local",
        password="testpass123!",
        role=User.Role.ORGANIZER,
    )


@pytest.fixture
def superuser(db):
    return User.objects.create_superuser(
        username="e2e_admin",
        email="e2e_admin@test.local",
        password="testpass123!",
        role=User.Role.OWNER,
    )


@pytest.fixture
def owner(db):
    """Non-superuser with OWNER role - can edit home page / site content."""
    return User.objects.create_user(
        username="e2e_owner",
        email="e2e_owner@test.local",
        password="testpass123!",
        role=User.Role.OWNER,
    )


# ---------------------------------------------------------------------------
# competition fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def approved_competition(db, organizer):
    return Competition.objects.create(
        title_ru="E2E Test Race RU",
        title_en="E2E Test Race",
        date_start=datetime.date(2026, 9, 1),
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
    )


@pytest.fixture
def competition_with_approval(db, organizer):
    return Competition.objects.create(
        title_ru="E2E Approval Race RU",
        title_en="E2E Approval Race",
        date_start=datetime.date(2026, 9, 1),
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
        registration_enabled=True,
        registration_mode=Competition.RegistrationMode.FREE,
        require_approval=True,
        require_payment=True,
    )


@pytest.fixture
def registration(db, competition_with_approval):
    return CompetitionRegistration.objects.create(
        competition=competition_with_approval,
        first_name="Ivan",
        last_name="Testov",
        birth_date=datetime.date(1990, 6, 15),
        gender="M",
    )


@pytest.fixture
def rejected_registration(db, competition_with_approval):
    return CompetitionRegistration.objects.create(
        competition=competition_with_approval,
        first_name="Pyotr",
        last_name="Rejected",
        birth_date=datetime.date(1985, 3, 10),
        gender="M",
        is_rejected=True,
        rejection_note="Test rejection",
    )


# ---------------------------------------------------------------------------
# discipline fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def road_category(db):
    return DisciplineCategory.objects.create(name_ru="Road", name_en="Road Cycling", order=1)


@pytest.fixture
def mtb_category(db):
    return DisciplineCategory.objects.create(name_ru="MTB", name_en="Mountain Bike", order=2)


@pytest.fixture
def road_discipline(db, road_category):
    return Discipline.objects.create(name_ru="Road Race", name_en="Road Race", category=road_category, order=1)


@pytest.fixture
def mtb_discipline(db, mtb_category):
    return Discipline.objects.create(
        name_ru="Cross-Country Olympic (XCO)",
        name_en="Cross-Country Olympic (XCO)",
        category=mtb_category,
        order=1,
    )


# ---------------------------------------------------------------------------
# location fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def location_tree(db):
    """Minimal 4-level tree: KZ > Region > Almaty > [hidden+real] + RU subtree."""
    from locations.models import Location

    kz = Location.add_root(name="KZ", name_ru="KZ", name_kk="KZ", name_en="KZ", sort_order=1)
    region = kz.add_child(name="KZ Region", name_ru="KZ Region", name_kk="KZ Region", name_en="KZ Region", sort_order=1)
    city = region.add_child(name="Almaty", name_ru="Almaty", name_kk="Almaty", name_en="Almaty", sort_order=1)
    hidden = city.add_child(
        name="Other Venue",
        name_ru="Other Venue",
        name_kk="Other Venue",
        name_en="Other Venue",
        sort_order=9999,
        is_hidden=True,
    )
    real = city.add_child(name="Velodrome", name_ru="Velodrome", name_kk="Velodrome", name_en="Velodrome", sort_order=1)
    ru = Location.add_root(name="RU", name_ru="RU", name_kk="RU", name_en="RU", sort_order=2)
    ru_region = ru.add_child(
        name="RU Region", name_ru="RU Region", name_kk="RU Region", name_en="RU Region", sort_order=1
    )
    ru_city = ru_region.add_child(name="Moscow", name_ru="Moscow", name_kk="Moscow", name_en="Moscow", sort_order=1)
    ru_hidden = ru_city.add_child(
        name="Other Venue",
        name_ru="Other Venue",
        name_kk="Other Venue",
        name_en="Other Venue",
        sort_order=9999,
        is_hidden=True,
    )
    return {
        "kz": Location.objects.get(pk=kz.pk),
        "region": Location.objects.get(pk=region.pk),
        "city": Location.objects.get(pk=city.pk),
        "hidden": Location.objects.get(pk=hidden.pk),
        "real": Location.objects.get(pk=real.pk),
        "ru": Location.objects.get(pk=ru.pk),
        "ru_hidden": Location.objects.get(pk=ru_hidden.pk),
    }


@pytest.fixture
def kz_competition(db, location_tree, organizer):
    """Approved competition in KZ / Almaty (hidden fallback venue)."""
    return Competition.objects.create(
        title_ru="KZ Race",
        date_start=datetime.date(2026, 7, 1),
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
        location=location_tree["hidden"],
    )


@pytest.fixture
def ru_competition(db, location_tree, organizer):
    """Approved competition in RU / Moscow (hidden fallback venue)."""
    return Competition.objects.create(
        title_ru="RU Race",
        date_start=datetime.date(2026, 7, 1),
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
        location=location_tree["ru_hidden"],
    )
