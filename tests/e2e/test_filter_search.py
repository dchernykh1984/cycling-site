"""E2E: the checkbox filters' search finds a name whichever script it is typed in.

The box folds the query and every name the way the site matches typed text elsewhere -- letters to
Latin with the server's table, then one spelling for what Cyrillic and Latin write differently -- so
"Kompass" typed in Cyrillic finds "Compass", and the other way round. The Cyrillic names are built from
code points: the source stays ASCII.
"""

import pytest
from playwright.sync_api import Page, expect

from agent.venues import fold_script
from cycling_site.text_search import search_words
from tests.e2e.conftest import open_filter_panel

_LIST_URL = "/ru/calendar/list/"


def _cyrillic(*codes: int) -> str:
    return "".join(map(chr, codes))


KOMPASS = _cyrillic(0x41A, 0x43E, 0x43C, 0x43F, 0x430, 0x441, 0x441)
KOMPAS = KOMPASS[:-1]
KHALYK = _cyrillic(0x425, 0x430, 0x43B, 0x44B, 0x43A)
ALMATY = _cyrillic(0x410, 0x43B, 0x43C, 0x430, 0x442, 0x44B)
QARAGHANDY = _cyrillic(0x49A, 0x430, 0x440, 0x430, 0x493, 0x430, 0x43D, 0x434, 0x44B)
KARAGANDA = _cyrillic(0x41A, 0x430, 0x440, 0x430, 0x433, 0x430, 0x43D, 0x434, 0x430)


def _venue(city, name: str):
    return city.add_child(name=name, name_ru=name, name_kk=name, name_en=name)


def _search(page: Page, level: int, text: str):
    page.locator(f"#mf-menu-{level} .mf-search").fill(text)
    return page.locator(f"#mf-menu-{level} li.mf-item-row")


@pytest.mark.django_db(transaction=True)
def test_a_venue_is_found_by_its_name_typed_in_the_other_script(page: Page, live_server, location_tree):
    from locations.models import Location

    city = Location.objects.get(pk=location_tree["city"].pk)
    compass, kompas, khalyk = (_venue(city, name) for name in ("Compass", KOMPAS, KHALYK))
    page.goto(f"{live_server.url}{_LIST_URL}")
    open_filter_panel(page)
    page.click("#mf-btn-4")
    for typed, found in ((KOMPASS, compass), ("Compass", kompas), ("Halyk", khalyk)):
        rows = _search(page, 4, typed)
        expect(rows.locator(f"input[value='{found.pk}']")).to_have_count(1)
    expect(_search(page, 4, "Halyk").locator(f"input[value='{compass.pk}']")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_a_place_is_found_by_its_name_in_another_language(page: Page, live_server, location_tree):
    """On the Kazakh page a city shows its Kazakh name, and it still answers to its Russian spelling."""
    from locations.models import Location

    region = Location.objects.get(pk=location_tree["region"].pk)
    city = region.add_child(name=KARAGANDA, name_ru=KARAGANDA, name_kk=QARAGHANDY, name_en="Karaganda")
    page.goto(f"{live_server.url}/kk/calendar/list/")
    open_filter_panel(page)
    page.click("#mf-btn-3")
    # Folded, the Kazakh spelling parts from the Russian after "kara"; the Russian name still answers.
    expect(_search(page, 3, KARAGANDA[:7]).locator(f"input[value='{city.pk}']")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_every_checkbox_filter_searches_the_same_way(page: Page, live_server, location_tree):
    """The event types' box is the same control: it folds its query as the places' box does."""
    from calendar_app.models import EventType

    cup = EventType.objects.create(name_ru="Compass Cup", name_kk="Compass Cup", name_en="Compass Cup", order=99)
    page.goto(f"{live_server.url}{_LIST_URL}")
    open_filter_panel(page)
    page.click("#et-btn-1")
    page.locator("#et-menu-1 .mf-search").fill(KOMPASS)
    expect(page.locator(f"#et-menu-1 li.mf-item-row input[value='{cup.pk}']")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_the_page_folds_words_as_the_server_does(page: Page, live_server, location_tree):
    """The browser's copy of the rule against its Python originals, on the cases each part exists for."""
    names = [
        "Compass",
        KOMPASS,
        KHALYK,
        "Halyk Bank",
        ALMATY,
        "Almaty",
        QARAGHANDY,
        "Center",
        "Maxim",
        "Wolf",
        "Qazaq Energy",
        "Sophia",
        "Udzhimchin",
        "Shymbulak 2",
        "Cafe-Bar",
    ]
    page.goto(f"{live_server.url}{_LIST_URL}")
    for name in names:
        expected = [fold_script(word) for word in search_words(name)]
        assert page.evaluate("text => window.cascadeSearchWords(text)", name) == expected, name
