"""An album's translated titles, optional event and event search across writing systems."""

import datetime
import json

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
    with page.expect_response(
        lambda response: response.request.method == "POST" and "/gallery/albums/" in response.url
    ):
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
    Competition.objects.create(
        title_ru="Gran Fondo second",
        date_start=DAY,
        status=Competition.Status.APPROVED,
    )
    _open(page, live_server, admin_user)
    query = page.locator("#gallery-event-query")
    query.fill(CYRILLIC_FONDO)
    expect(page.get_by_role("option")).to_have_count(2)
    query.press("ArrowUp")
    expect(query).to_have_attribute("aria-activedescendant", "gallery-event-option-1")
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
    _save(page)
    album.refresh_from_db()
    assert album.competition_id is None
    assert album.title == "My album"


@pytest.mark.django_db(transaction=True)
def test_escape_keeps_the_search_closed_when_a_late_response_arrives(
    page: Page, live_server, admin_user, gallery_event
):
    payload = {
        "results": [
            {
                "id": gallery_event.pk,
                "title": "Gran Fondo",
                "titles": {"ru": "Gran Fondo", "kk": "", "en": ""},
                "details": [],
            }
        ],
        "has_more": False,
    }
    # Hold an already-received response to reproduce Escape racing its asynchronous handling.
    page.add_init_script(
        "window.__searches = 0; var originalFetch = window.fetch;"
        "window.fetch = function(url, options) {"
        "if (!String(url).includes('/gallery/events/')) return originalFetch(url, options);"
        "window.__searches++;"
        "return new Promise(resolve => { window.__finishSearch = () => resolve({"
        "ok: true, json: () => Promise.resolve(" + json.dumps(payload) + ")"
        "}); }); };"
    )
    _open(page, live_server, admin_user)
    query = page.locator("#gallery-event-query")
    query.focus()
    page.wait_for_function("window.__searches === 1")
    query.fill("Gran")
    page.wait_for_function("window.__searches === 2")
    query.press("Escape")
    page.evaluate("window.__finishSearch()")
    expect(query).to_have_attribute("aria-expanded", "false")
    expect(page.get_by_role("listbox")).not_to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_enter_in_an_empty_search_does_not_submit_the_album(page: Page, live_server, admin_user):
    _open(page, live_server, admin_user)
    page.locator("#id_title_ru").fill("Draft waiting for an event")
    page.locator("#id_date").fill(DAY.isoformat())
    query = page.locator("#gallery-event-query")
    query.fill("No such event")
    message = page.locator("#gallery-event-picker").get_attribute("data-empty")
    expect(page.locator("#gallery-event-status")).to_have_text(message or "")
    query.press("Enter")
    page.wait_for_load_state("networkidle")
    expect(page).to_have_url(live_server.url + "/ru/gallery/albums/new/")
    assert not Album.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_picking_an_event_fills_every_title_and_the_date_and_they_stay_editable(
    page: Page, live_server, admin_user, gallery_event
):
    _open(page, live_server, admin_user)
    page.locator("#gallery-event-query").fill("Gran Fondo")
    page.get_by_role("option").filter(has_text="Gran Fondo").first.click()
    expect(page.locator("#id_title_ru")).to_have_value("Gran Fondo")
    expect(page.locator("#id_title_kk")).to_have_value("Gran Fondo KK")
    expect(page.locator("#id_title_en")).to_have_value("Gran Fondo EN")
    expect(page.locator("#id_date")).to_have_value(DAY.isoformat())
    page.locator("#id_title_ru").fill("Gran Fondo: the best shots")
    _save(page)
    album = Album.objects.get()
    titles = tuple(getattr(album, f"title_{language}") for language in ("ru", "en"))
    assert (*titles, album.date) == ("Gran Fondo: the best shots", "Gran Fondo EN", DAY)


@pytest.mark.django_db(transaction=True)
def test_a_title_typed_by_hand_survives_picking_an_event(page: Page, live_server, admin_user, gallery_event):
    _open(page, live_server, admin_user)
    page.locator("#id_title_ru").fill("My own title")
    page.locator("#gallery-event-query").fill("Gran Fondo")
    page.get_by_role("option").filter(has_text="Gran Fondo").first.click()
    expect(page.locator("#id_title_ru")).to_have_value("My own title")
    expect(page.locator("#id_title_kk")).to_have_value("Gran Fondo KK")


@pytest.mark.django_db(transaction=True)
def test_switching_events_on_an_album_replaces_only_what_came_from_the_old_one(
    page: Page, live_server, admin_user, gallery_event
):
    other = Competition.objects.create(
        title_ru="Tour Alatau",
        title_kk="Tour Alatau KK",
        title_en="Tour Alatau EN",
        date_start=DAY + datetime.timedelta(days=7),
        status=Competition.Status.APPROVED,
    )
    album = Album.objects.create(
        title_ru="Gran Fondo", title_kk="My Kazakh title", title_en="Gran Fondo EN", date=DAY, competition=gallery_event
    )
    _open(page, live_server, admin_user, f"/ru/gallery/albums/{album.pk}/edit/")
    page.locator("#gallery-event-query").fill("Tour Alatau")
    page.get_by_role("option").filter(has_text="Tour Alatau").first.click()
    expect(page.locator("#id_title_ru")).to_have_value("Tour Alatau")
    expect(page.locator("#id_title_kk")).to_have_value("My Kazakh title")
    expect(page.locator("#id_title_en")).to_have_value("Tour Alatau EN")
    expect(page.locator("#id_date")).to_have_value(other.date_start.isoformat())
