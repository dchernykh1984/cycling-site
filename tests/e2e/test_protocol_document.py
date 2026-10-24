"""A protocol drawn from its document reads on a phone and on a desktop, and stays live."""

import json
import re

import pytest
from django.utils.translation import gettext, override
from playwright.sync_api import Page, expect

from cycling_site.skins import registry
from protocols.document import parse
from protocols.models import Protocol
from tests.e2e.contrast import legibility

POLL_MS = 300
LOAD_TIMEOUT_MS = 1500


@pytest.fixture(autouse=True)
def fast_live_loop(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.PROTOCOL_POLL_INTERVAL_MS = POLL_MS
    settings.PROTOCOL_LOAD_TIMEOUT_MS = LOAD_TIMEOUT_MS


def _columns():
    return [
        {"id": "place", "label": "Place", "role": "place"},
        {"id": "bib", "label": "Bib", "role": "bib"},
        {"id": "name", "label": "Name", "role": "name"},
        {"id": "team", "label": "Team", "role": "team"},
        {"id": "year", "label": "Year", "priority": 3},
        {"id": "lap1", "label": "Lap time", "group": "Lap 1", "priority": 3},
        {"id": "lap1_s1", "label": "(1 split)", "group": "Lap 1", "toggle": "splits", "priority": 3},
        {"id": "lap1_s2", "label": "(2 split)", "group": "Lap 1", "toggle": "splits", "priority": 3},
        {"id": "result", "label": "Result", "sub_label": ["(gap)"], "role": "result"},
    ]


def _row(place, bib, name, group, *, status=None, note=None):
    row = {
        "group": group,
        "cells": {
            "place": place,
            "bib": bib,
            "name": name,
            "team": "Team " + name,
            "year": "1990",
            "lap1": "0:25:0" + bib[-1],
            "lap1_s1": "0:12:0" + bib[-1],
            "lap1_s2": "0:13:0" + bib[-1],
            "result": {"text": "1:00:0" + bib[-1], "sub": ["(+0:0" + bib[-1] + ")"]},
        },
    }
    if status:
        row["status"] = status
        row["cells"]["result"] = ""
    if note:
        row["note"] = note
    return row


def _raw(**overrides):
    data = {
        "schema": 1,
        "lang": "ru",
        "groups": [{"id": "M30", "label": "M30"}, {"id": "M40", "label": "M40"}],
        "toggles": [{"id": "splits", "label": "Splits", "default": True}],
        "header": [{"type": "field", "key": "weather", "label": "Weather", "value": "+14"}],
        "sections": [
            {
                "type": "table",
                "title": "Overall",
                "columns": _columns(),
                "rows": [
                    _row("1", "11", "Anna", "M30"),
                    _row("2", "22", "Boris", "M40"),
                    _row("DSQ", "33", "Vera", "M30", status="dsq", note="Cut the course"),
                ],
            }
        ],
        "footer": [{"type": "field", "key": "referee", "label": "Referee", "value": "R. Judge"}],
    }
    data.update(overrides)
    return data


def _document(**overrides):
    return parse(json.dumps(_raw(**overrides)).encode())


def _protocol(competition, document=None, *, live=True, file_hash="h1"):
    return Protocol.objects.create(
        competition=competition,
        protocol_type="absolute",
        is_live=live,
        file_hash=file_hash,
        document=document or _document(),
    )


def _republish(protocol, document, *, file_hash, live=True):
    protocol.document = document
    protocol.file_hash = file_hash
    protocol.is_live = live
    protocol.save()


def _open(page: Page, live_server, protocol, width=390):
    page.set_viewport_size({"width": width, "height": 800})
    page.goto(f"{live_server.url}/ru/protocols/{protocol.pk}/")
    expect(page.locator("#protocol-doc.protocol-js")).to_be_attached()


def _cell(page: Page, row_name: str, column_id: str):
    row = page.locator(".protocol-row", has_text=row_name)
    index = [c["id"] for c in _columns()].index(column_id)
    return row.locator(f'td[data-col="{index}"]')


def _no_page_scroll(page: Page):
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")


def _tr(text):
    with override("ru"):
        return gettext(text)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("width", [320, 390])
def test_phone_shows_place_number_name_and_result_and_the_rest_on_request(
    page: Page, live_server, approved_competition, width
):
    protocol = _protocol(approved_competition)
    _open(page, live_server, protocol, width)
    _no_page_scroll(page)
    for column in ("place", "bib", "name", "result"):
        expect(_cell(page, "Anna", column)).to_be_visible()
    for column in ("team", "year", "lap1"):
        expect(_cell(page, "Anna", column)).to_be_hidden()

    expand = page.locator(".protocol-row", has_text="Anna").locator(".protocol-row-expand")
    expect(expand).to_be_visible()
    expect(expand).to_have_attribute("aria-expanded", "false")
    expand.focus()
    page.keyboard.press("Enter")
    expect(expand).to_have_attribute("aria-expanded", "true")
    details = page.locator(".protocol-details")
    expect(details).to_contain_text("Team Anna")
    expect(details).to_contain_text("0:25:01")
    page.keyboard.press(" ")
    expect(details).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_table_without_priorities_or_roles_keeps_its_first_columns_on_a_phone(
    page: Page, live_server, approved_competition
):
    columns = [{"id": f"c{i}", "label": f"C{i}"} for i in range(6)]
    document = _document(
        groups=[],
        toggles=[],
        sections=[{"columns": columns, "rows": [{"cells": {f"c{i}": f"v{i}" for i in range(6)}}]}],
    )
    protocol = _protocol(approved_competition, document)
    _open(page, live_server, protocol, 320)
    row = page.locator(".protocol-row")
    for i in range(3):
        expect(row.locator(f'td[data-col="{i}"]')).to_be_visible()
    expect(row.locator('td[data-col="3"]')).to_be_hidden()
    row.locator(".protocol-row-expand").click()
    expect(page.locator(".protocol-details")).to_contain_text("v5")


@pytest.mark.django_db(transaction=True)
def test_search_by_name_and_number(page: Page, live_server, approved_competition):
    protocol = _protocol(approved_competition)
    _open(page, live_server, protocol)
    search = page.get_by_role("searchbox", name=_tr("Search by name or number"))
    search.fill("bor")
    expect(page.locator(".protocol-row:visible")).to_have_count(1)
    expect(page.locator(".protocol-row", has_text="Boris")).to_be_visible()
    search.fill("33")
    expect(page.locator(".protocol-row:visible")).to_have_count(1)
    expect(page.locator(".protocol-note", has_text="Cut the course")).to_be_visible()
    search.fill("nobody")
    expect(page.locator(".protocol-section")).to_be_hidden()


@pytest.mark.django_db(transaction=True)
def test_group_filter_works_in_one_mixed_table_without_a_group_column(page: Page, live_server, approved_competition):
    protocol = _protocol(approved_competition)
    _open(page, live_server, protocol, 1280)
    page.locator('.protocol-groups [data-group-id="M30"]').click()
    expect(page.locator(".protocol-row:visible")).to_have_count(2)
    expect(page.locator(".protocol-row", has_text="Boris")).to_be_hidden()
    page.locator('.protocol-groups [data-group-id="M30"]').evaluate("b => b.blur()")
    page.locator('.protocol-groups [data-group-id=""]').click()
    expect(page.locator(".protocol-row:visible")).to_have_count(3)


@pytest.mark.django_db(transaction=True)
def test_full_table_shows_every_column_and_scrolls_inside_its_box(page: Page, live_server, approved_competition):
    protocol = _protocol(approved_competition)
    _open(page, live_server, protocol, 390)
    mode = page.get_by_role("button", name=_tr("Full table"))
    mode.click()
    expect(mode).to_have_attribute("aria-pressed", "true")
    for column in ("team", "year", "lap1", "lap1_s1"):
        expect(_cell(page, "Anna", column)).to_be_visible()
    _no_page_scroll(page)
    mode.click()
    expect(_cell(page, "Anna", "team")).to_be_hidden()


@pytest.mark.django_db(transaction=True)
def test_desktop_shows_every_column_under_its_group_header(page: Page, live_server, approved_competition):
    protocol = _protocol(approved_competition)
    _open(page, live_server, protocol, 1280)
    for column in ("team", "year", "lap1", "lap1_s1", "lap1_s2"):
        expect(_cell(page, "Anna", column)).to_be_visible()
    expect(page.locator(".protocol-group-row th", has_text="Lap 1")).to_have_attribute("colspan", "3")
    expect(page.locator(".protocol-expand-col").first).to_be_hidden()


def _within(inner, outer):
    a, b = inner.bounding_box(), outer.bounding_box()
    return a["x"] >= b["x"] - 1 and a["x"] + a["width"] <= b["x"] + b["width"] + 1


@pytest.mark.django_db(transaction=True)
def test_group_headers_follow_the_columns_they_cover(page: Page, live_server, approved_competition):
    protocol = _protocol(approved_competition)
    _open(page, live_server, protocol, 1280)
    group = page.locator(".protocol-group-row th", has_text="Lap 1")
    splits = page.get_by_role("button", name="Splits")

    def check():
        result = _cell(page, "Anna", "result")
        result_header = page.locator('thead th[data-col="8"]')
        assert _within(result, result_header)
        if group.is_visible():
            for column in ("lap1", "lap1_s1", "lap1_s2"):
                cell = _cell(page, "Anna", column)
                if cell.is_visible():
                    assert _within(cell, group)
            assert not _within(result, group)

    check()
    splits.click()
    expect(_cell(page, "Anna", "lap1_s1")).to_be_hidden()
    expect(group).to_have_attribute("colspan", "1")
    check()
    page.set_viewport_size({"width": 390, "height": 800})
    expect(group).to_be_hidden()  # no column of Lap 1 left on a phone
    check()
    page.get_by_role("button", name=_tr("Full table")).click()
    expect(group).to_be_visible()
    check()
    splits.click()
    expect(group).to_have_attribute("colspan", "3")
    check()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(("width", "full"), [(1280, False), (390, False), (390, True)])
def test_disqualification_reason_is_always_readable(page: Page, live_server, approved_competition, width, full):
    protocol = _protocol(approved_competition)
    _open(page, live_server, protocol, width)
    if full:
        page.get_by_role("button", name=_tr("Full table")).click()
    expect(page.locator(".protocol-note", has_text="Cut the course")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_disqualification_reason_shows_in_a_table_of_main_columns_only(page: Page, live_server, approved_competition):
    document = _document(
        toggles=[],
        sections=[
            {
                "columns": [
                    {"id": "place", "label": "Place", "role": "place"},
                    {"id": "name", "label": "Name", "role": "name"},
                ],
                "rows": [{"status": "dsq", "note": "Cut the course", "cells": {"place": "DSQ", "name": "Vera"}}],
            }
        ],
    )
    protocol = _protocol(approved_competition, document)
    _open(page, live_server, protocol, 390)
    expect(page.locator(".protocol-row-expand")).to_be_hidden()
    expect(page.locator(".protocol-note", has_text="Cut the course")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_live_update_swaps_the_rows_and_keeps_the_readers_choices(page: Page, live_server, approved_competition):
    protocol = _protocol(approved_competition)
    _open(page, live_server, protocol, 1280)
    page.locator('.protocol-groups [data-group-id="M30"]').click()
    page.get_by_role("button", name="Splits").click()
    page.get_by_role("searchbox").fill("ann")

    updated = _document()
    updated["sections"][0]["rows"][0]["cells"]["name"] = "Anna Updated"
    _republish(protocol, updated, file_hash="h2")

    expect(page.locator(".protocol-row", has_text="Anna Updated")).to_be_visible(timeout=10_000)
    expect(page.get_by_role("searchbox")).to_have_value("ann")
    expect(page.locator('.protocol-groups [data-group-id="M30"]')).to_have_attribute("aria-pressed", "true")
    expect(page.get_by_role("button", name="Splits")).to_have_attribute("aria-pressed", "false")
    expect(_cell(page, "Anna Updated", "lap1_s1")).to_be_hidden()
    expect(page.locator(".protocol-row:visible")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_live_registries_change_and_the_choice_follows_the_id(page: Page, live_server, approved_competition):
    protocol = _protocol(approved_competition)
    _open(page, live_server, protocol, 1280)
    page.locator('.protocol-groups [data-group-id="M30"]').click()

    reordered = _document(
        groups=[{"id": "M40", "label": "M40"}, {"id": "M30", "label": "M30"}, {"id": "W", "label": "W"}],
        toggles=[{"id": "splits", "label": "Splits"}, {"id": "stats", "label": "Stats", "default": False}],
    )
    reordered["sections"][0]["columns"].append({"id": "rank", "label": "Rank", "toggle": "stats"})
    _republish(protocol, reordered, file_hash="h2")
    expect(page.locator('.protocol-groups [data-group-id="W"]')).to_be_visible(timeout=10_000)
    expect(page.locator('.protocol-groups [data-group-id="M30"]')).to_have_attribute("aria-pressed", "true")
    expect(page.locator(".protocol-row", has_text="Boris")).to_be_hidden()
    expect(page.locator(".protocol-row:visible")).to_have_count(2)
    stats = page.get_by_role("button", name="Stats")
    expect(stats).to_have_attribute("aria-pressed", "false")
    expect(page.locator('thead th[data-toggle-id="stats"]')).to_be_hidden()

    without = _raw(groups=[{"id": "M40", "label": "M40"}], toggles=[])
    for row in without["sections"][0]["rows"]:
        row["group"] = "M40"
    for column in without["sections"][0]["columns"]:
        column.pop("toggle", None)
    _republish(protocol, parse(json.dumps(without).encode()), file_hash="h3")
    expect(page.locator('.protocol-groups [data-group-id="M30"]')).to_have_count(0, timeout=10_000)
    expect(page.locator('.protocol-groups [data-group-id=""]')).to_have_attribute("aria-pressed", "true")
    expect(page.locator(".protocol-row:visible")).to_have_count(3)
    expect(page.get_by_role("button", name="Splits")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_failed_fragment_keeps_the_table_and_retries(page: Page, live_server, approved_competition):
    protocol = _protocol(approved_competition)
    _open(page, live_server, protocol, 1280)
    failing = {"on": True}
    page.route(
        re.compile(r".*/protocols/\d+/fragment/"),
        lambda route: route.fulfill(status=500, body="Server Error") if failing["on"] else route.continue_(),
    )
    updated = _document()
    updated["sections"][0]["rows"][0]["cells"]["name"] = "Anna Final"
    _republish(protocol, updated, file_hash="h2", live=False)
    expect(page.locator("#live-error")).to_be_visible(timeout=10_000)
    expect(page.locator(".protocol-row", has_text="Anna")).to_be_visible()
    expect(page.locator("#live-banner")).not_to_have_text(_tr("Final results"))
    failing["on"] = False
    expect(page.locator(".protocol-row", has_text="Anna Final")).to_be_visible(timeout=10_000)
    expect(page.locator("#live-banner")).to_have_text(_tr("Final results"))


@pytest.mark.django_db(transaction=True)
def test_live_decides_on_the_fragment_not_on_the_hint(page: Page, live_server, approved_competition):
    protocol = _protocol(approved_competition)
    _open(page, live_server, protocol, 1280)
    page.route(
        re.compile(r".*/api/protocols/\d+/last_updated/"),
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"last_updated": "", "file_hash": "older-final", "is_live": False, "shown": "document"}),
        ),
    )
    updated = _document()
    updated["sections"][0]["rows"][0]["cells"]["name"] = "Anna Newer"
    _republish(protocol, updated, file_hash="h2", live=True)
    expect(page.locator(".protocol-row", has_text="Anna Newer")).to_be_visible(timeout=10_000)
    page.wait_for_timeout(4 * POLL_MS)
    expect(page.locator("#live-banner")).not_to_have_text(_tr("Final results"))


@pytest.mark.django_db(transaction=True)
def test_protocol_that_became_html_reloads_into_a_frame(page: Page, live_server, approved_competition, tmp_path):
    from django.core.files.base import ContentFile

    protocol = _protocol(approved_competition)
    _open(page, live_server, protocol, 1280)
    protocol.html_file.save("p.html", ContentFile(b"<html><body><p>Plain HTML B</p></body></html>"), save=False)
    _republish(protocol, None, file_hash="h2", live=True)
    expect(page.frame_locator("#protocol-frame").get_by_text("Plain HTML B")).to_be_visible(timeout=10_000)
    expect(page.locator("#protocol-doc")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_html_page_reloads_into_the_document_published_meanwhile(page: Page, live_server, approved_competition):
    from django.core.files.base import ContentFile

    protocol = Protocol(competition=approved_competition, protocol_type="absolute", is_live=True, file_hash="h1")
    protocol.html_file.save("p.html", ContentFile(b"<html><body><p>Plain HTML A</p></body></html>"), save=True)
    page.goto(f"{live_server.url}/ru/protocols/{protocol.pk}/")
    expect(page.frame_locator("#protocol-frame").get_by_text("Plain HTML A")).to_be_visible()
    # The hint names a newer HTML upload; by the time the frame loads, a document with HTML is final.
    _republish(protocol, _document(), file_hash="h2", live=False)
    expect(page.locator(".protocol-row", has_text="Anna")).to_be_visible(timeout=10_000)
    expect(page.locator("iframe")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_a_document_at_the_size_limit_opens_and_searches_on_a_phone(page: Page, live_server, approved_competition):
    columns = [{"id": "place", "role": "place"}, {"id": "name", "role": "name"}] + [
        {"id": f"c{i}", "label": f"C{i}"} for i in range(18)
    ]
    rows = [{"cells": {"place": str(i), "name": f"Rider {i}", "c0": "x"}} for i in range(5000)]
    document = _document(groups=[], toggles=[], sections=[{"columns": columns, "rows": rows}])
    protocol = _protocol(approved_competition, document, live=False)
    _open(page, live_server, protocol, 390)
    page.get_by_role("searchbox").fill("rider 4999")
    expect(page.locator(".protocol-row:visible")).to_have_count(1, timeout=20_000)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("theme", list(registry()))
def test_secondary_text_stays_legible_in_every_skin(page: Page, live_server, approved_competition, theme):
    protocol = _protocol(approved_competition)
    host = live_server.url.split("//")[1].split(":")[0]
    page.context.add_cookies([{"name": "skin", "value": theme, "domain": host, "path": "/"}])
    _open(page, live_server, protocol, 1280)
    for locator in (
        page.locator(".protocol-row.status-dsq td").nth(3),
        page.locator(".protocol-note td"),
        _cell(page, "Anna", "result").locator(".protocol-cell-sub"),
        page.locator("thead .protocol-cell-sub"),
    ):
        assert legibility(locator) >= 4.5, (theme, locator)


@pytest.mark.django_db(transaction=True)
def test_a_table_of_one_switched_column_shows_it_on_a_phone(page: Page, live_server, approved_competition):
    document = parse(
        json.dumps(
            {
                "schema": 1,
                "toggles": [{"id": "t", "label": "T", "default": True}],
                "sections": [
                    {
                        "columns": [{"id": "result", "label": "Time", "toggle": "t"}],
                        "rows": [{"cells": {"result": "1:00"}}],
                    }
                ],
            }
        ).encode()
    )
    protocol = _protocol(approved_competition, document)
    _open(page, live_server, protocol, 390)
    expect(page.locator('.protocol-row td[data-col="0"]')).to_be_visible()
    expect(page.locator(".protocol-row-expand")).to_be_hidden()


@pytest.mark.django_db(transaction=True)
def test_switching_off_the_only_main_column_brings_others_on_a_phone(page: Page, live_server, approved_competition):
    document = parse(
        json.dumps(
            {
                "schema": 1,
                "toggles": [{"id": "t", "label": "T", "default": True}],
                "sections": [
                    {
                        "columns": [
                            {"id": "result", "label": "Time", "role": "result", "toggle": "t"},
                            {"id": "team", "label": "Team"},
                            {"id": "city", "label": "City"},
                        ],
                        "rows": [{"cells": {"result": "1:00", "team": "Team A", "city": "Almaty"}}],
                    }
                ],
            }
        ).encode()
    )
    protocol = _protocol(approved_competition, document)
    _open(page, live_server, protocol, 390)
    row = page.locator(".protocol-row")
    expect(row.locator('td[data-col="0"]')).to_be_visible()
    expect(row.locator('td[data-col="1"]')).to_be_hidden()
    page.get_by_role("button", name="T", exact=True).click()
    expect(row.locator('td[data-col="0"]')).to_be_hidden()
    expect(row.locator('td[data-col="1"]')).to_be_visible()
    expect(row.locator('td[data-col="2"]')).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_the_link_to_the_original_follows_each_live_update(page: Page, live_server, approved_competition):
    from django.core.files.base import ContentFile

    protocol = _protocol(approved_competition)
    protocol.html_file.save("p.html", ContentFile(b"<html><body>orig</body></html>"), save=True)
    _open(page, live_server, protocol, 1280)
    expect(page.locator("#protocol-original")).to_be_visible()

    # Data only now: the original is gone, and so is its link.
    protocol.html_file = ""
    _republish(protocol, _document(), file_hash="h2", live=True)
    expect(page.locator("#protocol-original")).to_have_count(0, timeout=10_000)

    # Both again, and final: the link comes back with the final results.
    protocol.html_file.save("p2.html", ContentFile(b"<html><body>orig 2</body></html>"), save=False)
    _republish(protocol, _document(), file_hash="h3", live=False)
    expect(page.locator("#live-banner")).to_have_text(_tr("Final results"), timeout=10_000)
    expect(page.locator("#protocol-original")).to_have_attribute("href", f"/ru/protocols/{protocol.pk}/html/?v=h3")


def _html_page(page: Page, live_server, competition):
    from django.core.files.base import ContentFile

    protocol = Protocol(competition=competition, protocol_type="absolute", is_live=True, file_hash="h1")
    protocol.html_file.save("p.html", ContentFile(b"<html><body><p>Plain HTML A</p></body></html>"), save=True)
    page.goto(f"{live_server.url}/ru/protocols/{protocol.pk}/")
    expect(page.frame_locator("#protocol-frame").get_by_text("Plain HTML A")).to_be_visible()
    return protocol


@pytest.mark.django_db(transaction=True)
def test_html_page_moves_to_a_data_only_protocol(page: Page, live_server, approved_competition):
    protocol = _html_page(page, live_server, approved_competition)
    protocol.html_file = ""
    _republish(protocol, _document(), file_hash="h2", live=False)
    expect(page.locator(".protocol-row", has_text="Anna")).to_be_visible(timeout=10_000)
    expect(page.locator("iframe")).to_have_count(0)
    expect(page.locator("#live-banner, .alert-success").first).to_have_text(_tr("Final results"))


@pytest.mark.django_db(transaction=True)
def test_html_page_moves_to_data_only_published_between_the_hint_and_the_load(
    page: Page, live_server, approved_competition
):
    protocol = _html_page(page, live_server, approved_competition)
    # The hint still names a new HTML upload; by the time the frame asks, the HTML is gone.
    page.route(
        re.compile(r".*/api/protocols/\d+/last_updated/"),
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"last_updated": "", "file_hash": "h-html", "is_live": True, "shown": "html"}),
        ),
    )
    protocol.html_file = ""
    _republish(protocol, _document(), file_hash="h2", live=False)
    expect(page.locator(".protocol-row", has_text="Anna")).to_be_visible(timeout=10_000)
    expect(page.locator("iframe")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_a_stalled_fragment_does_not_stall_a_drawn_protocol(page: Page, live_server, approved_competition):
    protocol = _protocol(approved_competition)
    _open(page, live_server, protocol, 1280)
    stalled: list = []

    def first_one_hangs(route):
        if not stalled:
            stalled.append(route)
        else:
            route.continue_()

    page.route(re.compile(r".*/protocols/\d+/fragment/"), first_one_hangs)
    updated = _document()
    updated["sections"][0]["rows"][0]["cells"]["name"] = "Anna After"
    _republish(protocol, updated, file_hash="h2", live=False)
    expect(page.locator(".protocol-row", has_text="Anna After")).to_be_visible(timeout=15_000)
    expect(page.locator("#live-banner")).to_have_text(_tr("Final results"))
    assert stalled


@pytest.mark.django_db(transaction=True)
def test_html_page_loads_html_when_the_hinted_document_is_gone_again(page: Page, live_server, approved_competition):
    from django.core.files.base import ContentFile

    protocol = _html_page(page, live_server, approved_competition)
    # The hint names a document, but by the time the page asks, the protocol is HTML again.
    page.route(
        re.compile(r".*/api/protocols/\d+/last_updated/"),
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"last_updated": "", "file_hash": "h-doc", "is_live": True, "shown": "document"}),
        ),
    )
    protocol.html_file.save("p2.html", ContentFile(b"<html><body><p>Plain HTML B</p></body></html>"), save=False)
    _republish(protocol, None, file_hash="h2", live=True)
    expect(page.frame_locator("#protocol-frame").get_by_text("Plain HTML B")).to_be_visible(timeout=10_000)
    expect(page.locator("#live-error")).to_be_hidden()


def _height(locator) -> float:
    box = locator.bounding_box()
    assert box is not None
    return box["height"]


@pytest.mark.django_db(transaction=True)
def test_many_long_groups_keep_to_one_row_on_a_phone(page: Page, live_server, approved_competition):
    names = [f"M{age}-{age + 9} - Men born {2004 - age}-{1995 - age}" for age in range(18, 90, 8)]
    document = _raw(groups=[{"id": n, "label": n} for n in names])
    for row in document["sections"][0]["rows"]:
        row["group"] = names[0]
    protocol = _protocol(approved_competition, parse(json.dumps(document).encode()))
    _open(page, live_server, protocol, 390)
    groups = page.locator(".protocol-groups")
    assert _height(groups) < 60
    assert groups.evaluate("el => el.scrollWidth > el.clientWidth")
    switches = page.locator(".protocol-switches")
    assert _height(switches) < 60
    _no_page_scroll(page)
    # The last chip is still reachable: it scrolls into view and filters.
    page.locator(f'.protocol-groups [data-group-id="{names[-1]}"]').click()
    expect(page.locator(".protocol-row:visible")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_the_group_headings_row_hides_when_none_of_its_groups_is_shown(page: Page, live_server, approved_competition):
    protocol = _protocol(approved_competition)
    _open(page, live_server, protocol, 390)
    expect(page.locator(".protocol-group-row")).to_be_hidden()
    page.set_viewport_size({"width": 1280, "height": 800})
    expect(page.locator(".protocol-group-row")).to_be_visible()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("width", [320, 390])
def test_the_result_fits_a_phone_without_scrolling_the_table(page: Page, live_server, approved_competition, width):
    protocol = _protocol(approved_competition)
    _open(page, live_server, protocol, width)
    for name in ("Anna", "Boris"):
        box = _cell(page, name, "result").bounding_box()
        assert box is not None and box["x"] + box["width"] <= width
    wrap = page.locator(".protocol-table-wrap").first
    assert wrap.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
