"""A knockout drawn from its document (issue #454): its stages side by side on a desktop, each heat
level with the two it was fed by, and a list with the final first on a phone."""

import json

import pytest
from playwright.sync_api import Page, expect

from cycling_site.skins import registry
from protocols.document import parse
from protocols.models import Protocol
from tests.e2e.contrast import legibility


@pytest.fixture(autouse=True)
def _media(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)


def _columns():
    return [
        {"id": "place", "label": "Place", "role": "place"},
        {"id": "bib", "label": "Bib", "role": "bib", "priority": 3},
        {"id": "name", "label": "Name", "role": "name"},
        {"id": "year", "label": "Year", "priority": 8},
        {"id": "team", "label": "Team", "role": "team", "priority": 6},
        {"id": "city", "label": "City", "priority": 7},
        {"id": "result", "label": "Result", "role": "result", "priority": 4},
    ]


def _heat(title, names):
    rows = [
        {
            "cells": {
                "place": str(i + 1),
                "bib": str(100 + i),
                "name": name,
                "year": "2012",
                "team": f"Team {name}",
                "city": "Springfield",
                "result": f"0:00:3{i}.0",
            }
        }
        for i, name in enumerate(names)
    ]
    return {"type": "table", "title": title, "columns": _columns(), "rows": rows}


def _riders(prefix, count=4):
    return [f"{prefix} Rider{n}" for n in range(1, count + 1)]


def _ladder(rounds, *, title="Boys", group=None, seated_rounds=None):
    """A ladder of four riders a heat: the first round seated, the later ones seated up to
    ``seated_rounds`` (all of them by default) and empty after that."""
    seated_rounds = rounds if seated_rounds is None else seated_rounds
    stages = []
    for stage in range(rounds):
        heats = 2 ** (rounds - stage - 1)
        name = "Final" if heats == 1 else f"1/{heats} final"
        stages.append(
            {
                "title": name,
                "sections": [
                    _heat(
                        f"{name} {n + 1}" if heats > 1 else name,
                        _riders(f"S{stage}H{n}") if stage < seated_rounds else [],
                    )
                    for n in range(heats)
                ],
            }
        )
    ladder = {"type": "ladder", "title": title, "sections": stages}
    if group:
        ladder["group"] = group
    return ladder


def _protocol(competition, *ladders, groups=()):
    raw = {"schema": 1, "lang": "en", "groups": [{"id": g, "label": g} for g in groups], "sections": list(ladders)}
    return Protocol.objects.create(
        competition=competition,
        protocol_type="group",
        is_live=False,
        file_hash="h1",
        document=parse(json.dumps(raw).encode()),
    )


def _open(page: Page, live_server, protocol, width):
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(f"{live_server.url}/en/protocols/{protocol.pk}/")
    expect(page.locator("#protocol-doc.protocol-js")).to_be_attached()


def _box(locator):
    box = locator.bounding_box()
    assert box is not None, locator
    return box


def _middle(locator):
    box = _box(locator)
    return box["y"] + box["height"] / 2


def _heat_box(page: Page, title):
    # By its table's name: a heat named as its stage ("Final") shows no heading of its own.
    return page.locator(".protocol-ladder-heat", has=page.get_by_role("table", name=title, exact=True))


def _no_page_scroll(page: Page):
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")


@pytest.mark.django_db(transaction=True)
def test_the_stages_stand_side_by_side_on_a_desktop(page: Page, live_server, approved_competition):
    _open(page, live_server, _protocol(approved_competition, _ladder(2)), 1280)
    semis, final = page.locator(".protocol-ladder-stage").all()
    assert _box(semis)["x"] + _box(semis)["width"] <= _box(final)["x"]
    # The final sits level with the middle of the two semi-finals that fed it.
    between = (_middle(_heat_box(page, "1/2 final 1")) + _middle(_heat_box(page, "1/2 final 2"))) / 2
    assert abs(_middle(_heat_box(page, "Final")) - between) <= 2
    expect(page.locator(".protocol-ladder-join")).to_be_visible()
    _no_page_scroll(page)


@pytest.mark.django_db(transaction=True)
def test_the_final_comes_first_on_a_phone(page: Page, live_server, approved_competition):
    _open(page, live_server, _protocol(approved_competition, _ladder(2)), 390)
    assert _box(_heat_box(page, "Final"))["y"] < _box(_heat_box(page, "1/2 final 1"))["y"]
    assert _box(_heat_box(page, "1/2 final 1"))["y"] < _box(_heat_box(page, "1/2 final 2"))["y"]
    expect(page.locator(".protocol-ladder-join")).to_be_hidden()
    _no_page_scroll(page)


@pytest.mark.django_db(transaction=True)
def test_a_heat_nobody_is_seated_in_is_an_empty_box_on_a_desktop_and_left_out_on_a_phone(
    page: Page, live_server, approved_competition
):
    protocol = _protocol(approved_competition, _ladder(2, seated_rounds=1))
    _open(page, live_server, protocol, 1280)
    expect(page.locator(".protocol-ladder-vacant")).to_be_visible()
    expect(page.get_by_role("heading", name="Final", exact=True).first).to_be_visible()
    _open(page, live_server, protocol, 390)
    expect(page.locator(".protocol-ladder-vacant")).to_be_hidden()
    expect(page.get_by_role("heading", name="Final", exact=True)).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_an_empty_heat_matches_no_search_and_keeps_its_room(page: Page, live_server, approved_competition):
    _open(page, live_server, _protocol(approved_competition, _ladder(2, seated_rounds=1)), 1280)
    vacant = page.locator(".protocol-ladder-vacant")
    expect(vacant).to_be_visible()
    page.locator(".protocol-search").fill("S0H1 Rider2")
    expect(vacant).to_be_hidden()
    expect(_heat_box(page, "1/2 final 1")).to_be_hidden()
    expect(_heat_box(page, "1/2 final 2")).to_be_visible()
    # Hidden, not taken out: its column keeps its room beside the heat found.
    assert _box(page.locator(".protocol-ladder-slot.is-vacant"))["height"] > 0


@pytest.mark.django_db(transaction=True)
def test_a_narrow_column_keeps_place_and_name_and_opens_the_rest_on_a_tap(
    page: Page, live_server, approved_competition
):
    # Five rounds: sixteen heats in the first, more columns than a desktop has room for.
    _open(page, live_server, _protocol(approved_competition, _ladder(5)), 1280)
    heat = _heat_box(page, "1/16 final 1")
    expect(heat.locator("th.role-place")).to_be_visible()
    expect(heat.locator("th.role-name")).to_be_visible()
    expect(heat.locator("th.role-result")).to_be_hidden()
    expect(heat.locator("th", has_text="Year")).to_be_hidden()
    # The ladder scrolls sideways inside its box, never the page.
    stages = page.locator(".protocol-ladder-stages")
    assert stages.evaluate("el => el.scrollWidth > el.clientWidth + 1")
    _no_page_scroll(page)
    heat.locator(".protocol-row", has_text="S0H0 Rider1").locator(".protocol-row-expand").click()
    expect(heat.locator(".protocol-details")).to_contain_text("Result")


@pytest.mark.django_db(transaction=True)
def test_a_search_leaves_every_stage_where_it_stood(page: Page, live_server, approved_competition):
    _open(page, live_server, _protocol(approved_competition, _ladder(3)), 1280)
    stages = page.locator(".protocol-ladder-stage")
    before = [_box(stage)["x"] for stage in stages.all()]
    joins = page.locator(".protocol-ladder-join")
    expect(joins.first).to_be_visible()
    page.locator(".protocol-search").fill("S0H2 Rider3")
    expect(_heat_box(page, "1/4 final 1")).to_be_hidden()
    expect(_heat_box(page, "1/4 final 3")).to_be_visible()
    expect(stages).to_have_count(3)
    assert [_box(stage)["x"] for stage in stages.all()] == before
    # Lines to the heats the search hid would lead nowhere: none while it is on.
    for join in joins.all():
        expect(join).to_be_hidden()
    page.locator(".protocol-search").fill("")
    expect(joins.first).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_the_category_filter_shows_one_ladder(page: Page, live_server, approved_competition):
    boys = _ladder(2, title="Boys", group="B")
    girls = _ladder(2, title="Girls", group="G")
    _open(page, live_server, _protocol(approved_competition, boys, girls, groups=("B", "G")), 1280)
    page.locator('.protocol-groups [data-group-id="G"]').click()
    expect(page.locator(".protocol-ladder", has_text="Boys")).to_be_hidden()
    expect(page.locator(".protocol-ladder", has_text="Girls")).to_be_visible()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("theme", list(registry()))
def test_the_stage_and_heat_names_stay_legible_in_every_skin(page: Page, live_server, approved_competition, theme):
    protocol = _protocol(approved_competition, _ladder(2))
    host = live_server.url.split("//")[1].split(":")[0]
    page.context.add_cookies([{"name": "skin", "value": theme, "domain": host, "path": "/"}])
    _open(page, live_server, protocol, 1280)
    for locator in (
        page.locator(".protocol-ladder-stage-title").first,
        page.locator(".protocol-ladder-heat-title").first,
    ):
        assert legibility(locator) >= 4.5, (theme, locator)
