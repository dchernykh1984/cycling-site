import datetime
import os
import re

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


def inject_session(page, live_server, user):
    # django_language=ru cookie is read by LocaleFallbackMiddleware for non-i18n paths
    # (e.g. /calendar/) so CI browsers with Accept-Language: en-US see Russian content.
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


def switch_locale(page, locale):
    # Navigate directly to the locale-prefixed URL.  Setting django_language cookie alone
    # does not work for paths inside i18n_patterns with prefix_default_language=False:
    # LocaleMiddleware ignores the cookie and forces LANGUAGE_CODE to the default locale
    # for any URL that lacks a language prefix.
    from urllib.parse import urlparse

    parsed = urlparse(page.url)
    # Strip any existing non-default (/kk/ or /en/) prefix so we can add the new one.
    path = re.sub(r"^/(kk|en)/", "/", parsed.path) or "/"
    new_path = path if locale == "ru" else f"/{locale}{path}"
    page.goto(f"{parsed.scheme}://{parsed.netloc}{new_path}")


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
