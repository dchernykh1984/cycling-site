"""An album's translated titles, optional event and event search across writing systems."""

import datetime

import pytest
from playwright.sync_api import Page, expect

from calendar_app.models import Competition, Discipline, DisciplineCategory
from gallery.models import Album
from tests.e2e.conftest import inject_session

CYRILLIC_FONDO = "\u0413\u0440\u0430\u043d \u0424\u043e\u043d\u0434\u043e"
DAY = datetime.date(2026, 10, 23)


@pytest.fixture
def gallery_event(db):
    event = Competition.objects.create(
        title_ru="Gran Fondo",
        title_kk="Gran Fondo KK",
        title_en="Gran Fondo EN",
        date_start=DAY,
        status=Competition.Status.APPROVED,
    )
    category = DisciplineCategory.objects.create(name_ru="Cycling")
    event.disciplines.add(Discipline.objects.create(name_ru="Road", category=category))
    return event


def _open(page, live_server, admin_user, path="/ru/gallery/albums/new/"):
    inject_session(page, live_server, admin_user)
    page.goto(live_server.url + path)


def _save(page):
    page.locator('#album-form button[type="submit"]').click()
    page.wait_for_url("**/gallery/albums/*/edit/")


@pytest.mark.django_db(transaction=True)
def test_cyrillic_search_finds_a_latin_event_and_shows_its_facts(page: Page, live_server, admin_user, gallery_event):
    _open(page, live_server, admin_user)
    query = page.locator("#gallery-event-query")
    query.fill(CYRILLIC_FONDO)
    choice = page.get_by_role("option").filter(has_text="Gran Fondo")
    expect(choice).to_be_visible()
    expect(choice).to_contain_text("2026")
    expect(choice).to_contain_text("Cycling")
    expect(choice).to_contain_text("Road")
    choice.click()
    expect(page.locator("#id_competition")).to_have_value(str(gallery_event.pk))
    expect(page.locator("#gallery-selected-event")).to_contain_text("Road")
    _save(page)
    album = Album.objects.get()
    assert album.competition_id == gallery_event.pk
    assert tuple(getattr(album, f"title_{language}") for language in ("ru", "kk", "en")) == (
        "Gran Fondo",
        "Gran Fondo KK",
        "Gran Fondo EN",
    )
    page.goto(f"{live_server.url}/en/gallery/albums/{album.pk}/")
    expect(page.locator("#gallery-linked-event")).to_contain_text("Gran Fondo EN")
    expect(page.locator("#gallery-linked-event")).to_contain_text("Road")


@pytest.mark.django_db(transaction=True)
def test_an_album_without_an_event_keeps_three_titles(page: Page, live_server, admin_user):
    _open(page, live_server, admin_user)
    expect(page.locator("#id_competition")).to_have_value("")
    for language in ("ru", "kk", "en"):
        page.locator("#id_title_" + language).fill("Camp " + language.upper())
    page.locator("#id_date").fill(DAY.isoformat())
    _save(page)
    album = Album.objects.get()
    assert album.competition_id is None
    page.goto(f"{live_server.url}/kk/gallery/albums/{album.pk}/")
    expect(page.locator(".gallery-album-title")).to_have_text("Camp KK")
    expect(page.locator("#gallery-linked-event")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_the_event_can_be_picked_with_the_keyboard(page: Page, live_server, admin_user, gallery_event):
    _open(page, live_server, admin_user)
    query = page.locator("#gallery-event-query")
    query.fill(CYRILLIC_FONDO)
    expect(page.get_by_role("option")).to_be_visible()
    query.press("ArrowDown")
    expect(query).to_have_attribute("aria-activedescendant", "gallery-event-option-0")
    query.press("Enter")
    expect(page.locator("#id_competition")).to_have_value(str(gallery_event.pk))
    expect(query).to_have_attribute("aria-expanded", "false")


@pytest.mark.django_db(transaction=True)
def test_removing_an_event_keeps_the_album_and_its_titles(page: Page, live_server, admin_user, gallery_event):
    album = Album.objects.create(title_ru="My album", date=DAY, competition=gallery_event)
    _open(page, live_server, admin_user, f"/ru/gallery/albums/{album.pk}/edit/")
    expect(page.locator("#gallery-selected-event")).to_contain_text("Gran Fondo")
    page.locator("#gallery-clear-event").click()
    expect(page.locator("#id_competition")).to_have_value("")
    page.locator('#album-form button[type="submit"]').click()
    page.wait_for_load_state()
    album.refresh_from_db()
    assert album.competition_id is None
    assert album.title == "My album"
