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


def inject_session(page, live_server, user):
    """Inject a Django session cookie without navigating (avoids language-cookie side effects)."""
    client = Client()
    client.force_login(user)
    session_value = client.cookies["sessionid"].value
    host = live_server.url.split("//")[1].split(":")[0]
    page.context.add_cookies([{"name": "sessionid", "value": session_value, "domain": host, "path": "/"}])


def switch_locale(page, locale):
    """Activate the given locale for subsequent requests.

    Must be called after an initial page.goto() on the same origin.
    Sets django_language cookie via JS (reliable across all Playwright browsers)
    then reloads so the next Django request sees the cookie via LocaleMiddleware.
    """
    page.evaluate(f"document.cookie = 'django_language={locale}; path=/'")
    page.reload()


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
