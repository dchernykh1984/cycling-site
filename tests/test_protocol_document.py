"""The structured protocol document: what it accepts, what it refuses, and what it costs to show."""

import json
from pathlib import Path

import pytest
from django.core.files.base import ContentFile
from django.test import Client

from calendar_app.models import Competition
from protocols import document as doc
from protocols import rendering
from protocols.document import DocumentError, parse
from protocols.models import Protocol

SCHEMA_FILE = Path(__file__).resolve().parent.parent / "protocols" / "schema" / "protocol-document-v1.json"


def _raw(**fields) -> bytes:
    data = {"schema": 1, "sections": []}
    data.update(fields)
    return json.dumps(data).encode()


def _table(n_rows: int, n_columns: int, *, filled: bool = True, notes: int = 0) -> dict:
    columns = [{"id": f"c{i}"} for i in range(n_columns)]
    rows = []
    for r in range(n_rows):
        row: dict = {"cells": {"c0": str(r)} if filled else {}}
        if r < notes:
            row["note"] = "n"
        rows.append(row)
    return {"type": "table", "columns": columns, "rows": rows}


def test_committed_json_schema_matches_the_models():
    assert json.loads(SCHEMA_FILE.read_text()) == json.loads(json.dumps(doc.json_schema(), sort_keys=True))


def test_a_full_document_is_accepted_as_it_is():
    raw = {
        "schema": 1,
        "lang": "ru",
        "title": "Race",
        "generator": {"name": "FinishProtocolGenerator", "version": "1.0"},
        "header": [
            {"type": "text", "text": "2026-07-18, Medeu"},
            {"type": "field", "key": "weather", "label": "Weather", "value": "+14"},
            {"type": "html", "html": "<b>Sponsor</b>"},
        ],
        "groups": [{"id": "M30", "label": "M30"}],
        "toggles": [{"id": "splits", "label": "Splits", "default": True}],
        "sections": [
            {
                "type": "table",
                "title": "Group M30",
                "group": "M30",
                "columns": [
                    {"id": "place", "label": "Place", "role": "place"},
                    {"id": "lap1_s1", "label": "(1 split)", "group": "Lap 1", "toggle": "splits", "priority": 3},
                    {"id": "result", "label": "Time", "sub_label": ["(gap)"], "role": "result"},
                ],
                "rows": [
                    {"cells": {"place": "1", "result": {"text": "1:00:00", "sub": ["(+0:01)"], "strong": True}}},
                    {"status": "dsq", "note": "cut the course", "cells": {"place": "DSQ"}},
                ],
            }
        ],
        "footer": [{"type": "field", "key": "referee", "label": "Referee", "value": "A. B."}],
    }
    stored = parse(json.dumps(raw).encode())
    assert stored["sections"][0]["rows"][0]["cells"]["result"]["strong"] is True
    assert stored["groups"] == [{"id": "M30", "label": "M30"}]
    assert stored["header"][2]["html"] == "<b>Sponsor</b>"


def test_unknown_fields_are_ignored_and_unknown_kinds_kept():
    stored = parse(
        _raw(
            future_field=1,
            sections=[
                {
                    "type": "bracket",
                    "shape": "x",
                    "columns": [{"id": "a", "role": "wind", "kind": "new"}],
                    "rows": [{"cells": {"a": "1"}, "colour": "red"}],
                }
            ],
        )
    )
    assert "future_field" not in stored
    assert stored["sections"][0]["type"] == "bracket"
    assert stored["sections"][0]["columns"][0]["role"] == "wind"
    assert "colour" not in stored["sections"][0]["rows"][0]


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (b"not json", "not UTF-8 JSON"),
        (b"[1, 2]", "must be a JSON object"),
        (json.dumps({"schema": 2, "sections": []}).encode(), "Unsupported protocol document schema 2"),
        (json.dumps({"sections": []}).encode(), "Unsupported protocol document schema None"),
        (
            _raw(sections=[{"columns": [{"id": "a"}, {"id": "a"}], "rows": []}]),
            "column id 'a' is used twice",
        ),
        (
            _raw(sections=[{"columns": [{"id": "a"}], "rows": [{"cells": {"b": "1"}}]}]),
            "cells for columns that do not exist",
        ),
        (
            _raw(
                sections=[
                    {"columns": [{"id": "a"}], "rows": [{"cells": {"a": {"text": "x", "url": "javascript:alert(1)"}}}]}
                ]
            ),
            "http or https",
        ),
        (_raw(groups=[{"id": "M30"}, {"id": "M30"}]), "group id 'M30' is used twice"),
        (_raw(toggles=[{"id": "t"}, {"id": "t"}]), "toggle id 't' is used twice"),
        (
            _raw(sections=[{"columns": [{"id": "a"}], "rows": [{"group": "M40", "cells": {}}]}]),
            "row group 'M40' is not in the groups list",
        ),
        (_raw(sections=[{"group": "M40", "columns": [], "rows": []}]), "section group 'M40'"),
        (
            _raw(sections=[{"columns": [{"id": "a", "toggle": "splits"}], "rows": []}]),
            "names toggle 'splits', which is not in the toggles list",
        ),
        (
            _raw(
                sections=[
                    {"columns": [{"id": "a"}], "rows": [{"cells": {"a": {"sub": [{"text": "x", "toggle": "s"}]}}}]}
                ]
            ),
            "a line names toggle 's', which is not in the toggles list",
        ),
        (
            _raw(sections=[{"columns": [{"id": "a", "sub_label": [{"text": "x", "toggle": "s"}]}], "rows": []}]),
            "a line names toggle 's', which is not in the toggles list",
        ),
        (_raw(sections=[{"columns": [{"id": "a", "priority": 10}], "rows": []}]), "less than or equal to 9"),
        (
            _raw(
                sections=[
                    {
                        "type": "group",
                        "sections": [{"type": "group", "sections": [{"type": "group", "sections": [{}]}]}],
                    }
                ]
            ),
            "nested deeper than 3",
        ),
        (_raw(sections=[_table(5001, 1)]), "too many rows"),
        (_raw(sections=[_table(1, 201)]), "too many columns"),
        (_raw(lang="Russian"), "lang"),
        (_raw(sections=[{"columns": [{"id": "has space"}], "rows": []}]), "columns.0.id"),
    ],
)
def test_refused_documents_say_why(raw, message):
    with pytest.raises(DocumentError, match=message):
        parse(raw)


def test_budget_refuses_a_sparse_table_within_every_other_limit():
    # 1100 rows x 100 columns: inside the row and column limits, small on the wire, too big to draw.
    raw = _raw(sections=[_table(1100, 100)])
    assert len(raw) < 1024 * 1024
    with pytest.raises(DocumentError, match="110000 cells"):
        parse(raw)


def test_budget_boundary():
    parse(_raw(sections=[_table(1000, 100)]))  # exactly 100 000
    with pytest.raises(DocumentError, match="100001 cells"):
        parse(_raw(sections=[_table(1000, 100, notes=1)]))
    parse(_raw(sections=[_table(999, 100, notes=100)]))  # 99 900 + 100 notes


def test_budget_is_shared_by_every_table_of_the_document():
    with pytest.raises(DocumentError, match="112000 cells"):
        parse(_raw(sections=[_table(700, 80), {"type": "group", "sections": [_table(700, 80)]}]))


# --------------------------------------------------------------------------- drawing it


def _document(**fields) -> dict:
    data = {
        "schema": 1,
        "lang": "ru",
        "groups": [{"id": "M30", "label": "M30"}, {"id": "M40", "label": "M40"}],
        "sections": [
            {
                "type": "table",
                "title": "Overall",
                "columns": [
                    {"id": "place", "label": "Place", "role": "place"},
                    {"id": "name", "label": "Name", "role": "name"},
                    {"id": "result", "label": "Time", "role": "result"},
                ],
                "rows": [
                    {"group": "M30", "cells": {"place": "1", "name": "Ann <script>x</script>", "result": "1:00"}},
                    {"group": "M40", "cells": {"place": "2", "name": "Bob", "result": "1:01"}},
                ],
            }
        ],
    }
    data.update(fields)
    return parse(json.dumps(data).encode())


@pytest.fixture
def protocol(db, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    competition = Competition.objects.create(
        title_ru="Race", date_start="2026-01-01", status=Competition.Status.APPROVED
    )
    return Protocol.objects.create(
        competition=competition, protocol_type="absolute", is_live=True, file_hash="h1", document=_document()
    )


def test_document_page_draws_tables_not_a_frame(client: Client, protocol):
    body = client.get(f"/ru/protocols/{protocol.pk}/").content.decode()
    assert 'id="protocol-doc"' in body
    assert "<iframe" not in body
    assert 'data-format="document"' in body
    assert "protocol.css" in body
    assert "Ann &lt;script&gt;x&lt;/script&gt;" in body
    assert "<script>x</script>" not in body
    assert 'id="protocol-original"' not in body


def test_original_html_is_linked_only_when_it_came_with_the_document(client: Client, protocol):
    protocol.html_file.save("p.html", ContentFile(b"<html><body>orig</body></html>"), save=True)
    body = client.get(f"/ru/protocols/{protocol.pk}/").content.decode()
    assert f'href="/ru/protocols/{protocol.pk}/html/?v=h1"' in body
    assert 'id="protocol-original"' in body


def test_rows_carry_their_group_whatever_the_columns(client: Client, protocol):
    body = client.get(f"/ru/protocols/{protocol.pk}/").content.decode()
    assert body.count('data-group-id="M30"') == 2  # the chip and the row
    assert body.count('data-group-id="M40"') == 2


def test_one_category_offers_no_filter(client: Client, protocol):
    protocol.document = _document(
        groups=[{"id": "M30", "label": "M30"}],
        sections=[{"columns": [{"id": "name", "role": "name"}], "rows": [{"group": "M30", "cells": {"name": "Ann"}}]}],
    )
    protocol.save()
    body = client.get(f"/ru/protocols/{protocol.pk}/").content.decode()
    assert 'class="protocol-groups"' not in body
    assert body.count('data-group-id="M30"') == 1  # the row keeps its group, no chip offers it


def test_only_categories_with_riders_get_a_chip():
    rows = [{"group": g, "cells": {"name": g}} for g in ("M30", "W")]
    groups = [{"id": "M30"}, {"id": "M40"}, {"id": "W"}]
    view = rendering.build(_document(groups=groups, sections=[{"columns": [{"id": "name"}], "rows": rows}]), [])
    assert [g["id"] for g in view["groups"]] == ["M30", "W"]
    only_one = [{"group": "M40", "cells": {"name": "x"}}]
    view = rendering.build(_document(groups=groups, sections=[{"columns": [{"id": "name"}], "rows": only_one}]), [])
    assert view["groups"] == []


def test_nested_sections_pass_their_group_down():
    view = rendering.build(
        _document(
            groups=[{"id": "G"}],
            sections=[
                {"type": "group", "group": "G", "sections": [{"columns": [{"id": "a"}], "rows": [{"cells": {}}]}]}
            ],
        ),
        [],
    )
    assert view["sections"][0]["sections"][0]["table"]["rows"][0]["group"] == "G"


def test_a_table_without_priorities_keeps_its_first_columns_on_a_phone():
    view = rendering.build(
        _document(
            sections=[{"columns": [{"id": f"c{i}", "label": f"C{i}"} for i in range(5)], "rows": [{"cells": {}}]}]
        ),
        [],
    )
    priorities = [c["priority"] for c in view["sections"][0]["table"]["columns"]]
    assert priorities == [1, 1, 1, 2, 2]


def test_primary_roles_default_to_priority_one_and_others_to_two():
    view = rendering.build(_document(), [])
    assert [c["priority"] for c in view["sections"][0]["table"]["columns"]] == [1, 1, 1]
    view = rendering.build(
        _document(
            sections=[
                {
                    "columns": [{"id": "name", "label": "N", "role": "name"}, {"id": "team", "label": "T"}],
                    "rows": [{"cells": {}}],
                }
            ]
        ),
        [],
    )
    assert [c["priority"] for c in view["sections"][0]["table"]["columns"]] == [1, 2]


def test_search_looks_in_every_field_but_times_and_second_lines():
    view = rendering.build(
        _document(
            sections=[
                {
                    "columns": [{"id": c} for c in ("bib", "name", "team", "city", "lap", "result")],
                    "rows": [
                        {
                            "cells": {
                                "bib": "23",
                                "name": "Ann Lee",
                                "team": "Team X",
                                "city": "Almaty",
                                "lap": "0:12:23.4",
                                "result": {"text": "1:23:45", "sub": ["(+0:02.0)", "(2)"]},
                            }
                        }
                    ],
                }
            ]
        ),
        [],
    )
    assert view["sections"][0]["table"]["rows"][0]["search"] == "23 ann lee team x almaty"


def test_header_groups_merge_neighbouring_columns():
    view = rendering.build(
        _document(
            sections=[
                {
                    "columns": [
                        {"id": "p", "label": "P"},
                        {"id": "l1", "label": "L", "group": "Lap 1"},
                        {"id": "s1", "label": "S", "group": "Lap 1"},
                        {"id": "r", "label": "R"},
                    ],
                    "rows": [{"cells": {}}],
                }
            ]
        ),
        [],
    )
    runs = view["sections"][0]["table"]["header_groups"]
    assert [(r["label"], r["cols"]) for r in runs] == [("", "0"), ("Lap 1", "1 2"), ("", "3")]


def test_html_items_keep_only_this_sites_pictures():
    raw = {
        "header": [
            {
                "type": "html",
                "html": '<img src="https://evil.example/pixel.gif"><img src="http://testserver/media/logo.png">'
                '<script>alert(1)</script><a href="javascript:x">j</a>',
            }
        ]
    }
    view = rendering.build(_document(**raw), ["http://testserver"])
    html = view["header"][0]["html"]
    assert "evil.example" not in html
    assert "http://testserver/media/logo.png" in html
    assert "<script" not in html
    assert "javascript:" not in html


def test_unknown_section_kinds_are_drawn_by_their_shape():
    view = rendering.build(
        _document(
            sections=[
                {
                    "type": "bracket",
                    "title": "Final",
                    "sections": [{"type": "heat", "columns": [{"id": "a"}], "rows": [{"cells": {}}]}],
                }
            ]
        ),
        [],
    )
    assert view["sections"][0]["table"] is None
    assert view["sections"][0]["sections"][0]["table"] is not None


def test_language_note_only_when_the_protocol_is_in_another_language(client: Client, protocol):
    assert "protocol-language" not in client.get(f"/ru/protocols/{protocol.pk}/").content.decode()
    assert "protocol-language" in client.get(f"/en/protocols/{protocol.pk}/").content.decode()


def test_fragment_carries_the_state_of_the_row_it_was_drawn_from(client: Client, protocol):
    response = client.get(f"/ru/protocols/{protocol.pk}/fragment/")
    assert response.status_code == 200
    assert response["X-Protocol-Hash"] == "h1"
    assert response["X-Protocol-Live"] == "true"
    assert response["X-Protocol-Shown"] == "document"
    assert response["Cache-Control"] == "no-store"
    assert 'id="protocol-doc"' in response.content.decode()
    assert "<html" not in response.content.decode()


def test_fragment_of_a_protocol_that_lost_its_document_is_empty_and_says_html(client: Client, protocol):
    protocol.document = None
    protocol.is_live = False
    protocol.save()
    response = client.get(f"/ru/protocols/{protocol.pk}/fragment/")
    assert response.content == b""
    assert response["X-Protocol-Shown"] == "html"
    assert response["X-Protocol-Live"] == "false"


@pytest.mark.parametrize("flag", ["is_hidden", "is_deleted"])
def test_fragment_of_an_unpublished_event_is_404(client: Client, protocol, flag):
    setattr(protocol.competition, flag, True)
    protocol.competition.save()
    assert client.get(f"/ru/protocols/{protocol.pk}/fragment/").status_code == 404


def test_last_updated_says_the_protocol_is_shown_as_a_document(client: Client, protocol):
    assert client.get(f"/ru/api/protocols/{protocol.pk}/last_updated/").json()["shown"] == "document"


def test_notes_are_drawn_as_their_own_row(client: Client, protocol):
    protocol.document = _document(
        sections=[
            {
                "columns": [{"id": "place", "role": "place"}],
                "rows": [{"status": "dsq", "note": "cut\nno chip", "cells": {"place": "DSQ"}}],
            }
        ]
    )
    protocol.save()
    body = client.get(f"/ru/protocols/{protocol.pk}/").content.decode()
    assert 'class="protocol-row status-dsq"' in body
    assert '<tr class="protocol-note" data-for="row-1"><td colspan="2">cut<br>no chip</td></tr>' in body


def test_a_number_too_long_to_read_is_a_refused_document_not_a_crash():
    raw = b'{"schema": 1, "sections": [], "future": ' + b"1" * 5000 + b"}"
    with pytest.raises(DocumentError, match="not UTF-8 JSON"):
        parse(raw)


def test_deeply_nested_json_is_ignored_or_refused_never_a_crash():
    # How deep json can nest depends on the Python build: it is either read (and the
    # unknown field dropped) or refused as a document -- never any other error.
    raw = b'{"schema": 1, "sections": [], "x": ' + b"[" * 100_000 + b"]" * 100_000 + b"}"
    try:
        stored = parse(raw)
    except DocumentError as exc:
        assert "not UTF-8 JSON" in str(exc)
    else:
        assert "x" not in stored


def test_sections_nested_too_deep_for_the_validator_are_refused():
    nested: dict = {"type": "group"}
    for _ in range(2000):
        nested = {"type": "group", "sections": [nested]}
    with pytest.raises(DocumentError, match="nested deeper"):
        parse(json.dumps({"schema": 1, "sections": [nested]}).encode())


def test_a_picture_with_a_broken_address_is_dropped_and_the_protocol_still_opens(client: Client, protocol):
    protocol.document = _document(
        header=[{"type": "html", "html": '<p>Sponsor</p><img src="https://[broken/foo.png">'}]
    )
    protocol.save()
    for url in (f"/ru/protocols/{protocol.pk}/", f"/ru/protocols/{protocol.pk}/fragment/"):
        response = client.get(url)
        assert response.status_code == 200
        body = response.content.decode()
        assert "Sponsor" in body
        assert "[broken" not in body


def test_long_labels_and_roles_are_not_repeated_in_every_cell():
    columns = [{"id": f"c{i}", "label": "L" * 2000, "role": "r" * 2000} for i in range(100)]
    view = rendering.build(_document(sections=[{"columns": columns, "rows": [{"cells": {}}] * 100}]), [])
    body = str(view["sections"][0]["table"]["body"])
    assert "LLLL" not in body and "rrrr" not in body
    assert len(body) / (100 * 100) < 80  # bytes of markup per cell, whatever the labels


def test_an_unknown_status_is_drawn_as_other():
    view = rendering.build(
        _document(
            sections=[
                {
                    "columns": [{"id": "a"}],
                    "rows": [{"status": "x" * 2000, "cells": {}}, {"status": "DSQ", "cells": {}}],
                }
            ]
        ),
        [],
    )
    rows = view["sections"][0]["table"]["rows"]
    assert [r["status"] for r in rows] == ["other", "dsq"]


def test_the_fallback_columns_are_chosen_among_those_switched_on():
    one_switched_on = _document(
        toggles=[{"id": "t", "default": True}],
        sections=[{"columns": [{"id": "result", "label": "Time", "toggle": "t"}], "rows": [{"cells": {}}]}],
    )
    assert rendering.build(one_switched_on, [])["sections"][0]["table"]["columns"][0]["priority"] == 1
    off_first = _document(
        toggles=[{"id": "t", "default": False}],
        sections=[
            {
                "columns": [
                    {"id": "a", "label": "A", "toggle": "t"},
                    {"id": "b", "label": "B"},
                    {"id": "c", "label": "C"},
                ],
                "rows": [{"cells": {}}],
            }
        ],
    )
    priorities = [c["priority"] for c in rendering.build(off_first, [])["sections"][0]["table"]["columns"]]
    assert priorities == [2, 1, 1]


@pytest.mark.parametrize(
    "fields",
    [
        {"title": "x\u0000y"},
        {"header": [{"type": "field", "label": "Weather", "value": "+1\u00004"}]},
        {"groups": [{"id": "M\u000030"}]},
        {"sections": [{"columns": [{"id": "a", "label": "L\u0000"}], "rows": []}]},
        {"sections": [{"columns": [{"id": "a"}], "rows": [{"cells": {"a": {"text": "1", "sub": ["\u0000"]}}}]}]},
        {"sections": [{"columns": [{"id": "a"}], "rows": [{"note": "cut\u0000", "cells": {}}]}]},
    ],
)
def test_a_nul_character_in_a_stored_field_is_refused(fields):
    with pytest.raises(DocumentError, match="NUL character"):
        parse(_raw(**fields))


def test_a_nul_character_in_an_unknown_field_is_ignored_with_the_field():
    stored = parse(_raw(future="x\u0000y"))
    assert "future" not in stored


def test_a_column_with_no_heading_and_no_values_is_not_drawn():
    view = rendering.build(
        _document(
            sections=[
                {
                    "columns": [
                        {"id": "name", "label": "Name"},
                        {"id": "year", "label": ""},
                        {"id": "t", "label": "Time"},
                    ],
                    "rows": [
                        {"cells": {"name": "Ann", "t": "1:00"}},
                        {"cells": {"name": "Bob", "year": ""}},
                        {"cells": {"name": "Eve", "year": {"text": "", "sub": []}}},
                    ],
                }
            ]
        ),
        [],
    )
    table = view["sections"][0]["table"]
    assert [c["id"] for c in table["columns"]] == ["name", "t"]
    assert [c["index"] for c in table["columns"]] == [0, 1]
    assert 'data-col="2"' not in str(table["body"])


def test_an_unlabelled_column_with_values_is_kept():
    view = rendering.build(
        _document(sections=[{"columns": [{"id": "a", "label": ""}], "rows": [{"cells": {"a": "x"}}]}]), []
    )
    assert [c["id"] for c in view["sections"][0]["table"]["columns"]] == ["a"]


def test_a_rows_search_text_is_folded_to_one_script():
    # Cyrillic "Chernykh" and a Latin name: both end up as lower-case Latin words.
    cyrillic = "".join(map(chr, (0x427, 0x435, 0x440, 0x43D, 0x44B, 0x445)))
    view = rendering.build(
        _document(
            sections=[
                {
                    "columns": [{"id": "name", "role": "name"}],
                    "rows": [{"cells": {"name": f"{cyrillic} Denis"}}, {"cells": {"name": "Chernykh Denis"}}],
                }
            ]
        ),
        [],
    )
    rows = view["sections"][0]["table"]["rows"]
    assert [r["search"] for r in rows] == ["chernykh denis", "chernykh denis"]
    assert json.loads(view["fold"])[chr(0x427)] == "ch"


def test_a_toggle_hides_second_lines_under_a_cell_and_its_heading():
    stats = {"text": "0:00:00.0 (1)", "toggle": "stats", "strong": True}
    document = _document(
        toggles=[{"id": "stats", "label": "Stats"}],
        sections=[
            {
                "columns": [
                    {"id": "name", "role": "name"},
                    {
                        "id": "lap",
                        "label": "Lap 1",
                        "priority": 5,
                        "sub_label": ["(gap)", {"text": "(lap gap)", "toggle": "stats"}],
                    },
                ],
                "rows": [{"cells": {"name": "Ann", "lap": {"text": "0:25:32.4", "sub": ["(0:25:32.4)", stats]}}}],
            }
        ],
    )
    table = rendering.build(document, [])["sections"][0]["table"]
    assert table["columns"][1]["priority"] == 5
    body = str(table["body"])
    assert '<br><small class="protocol-cell-sub">(0:25:32.4)</small>' in body
    assert (
        '<span class="protocol-line" data-toggle-id="stats"><br><small class="protocol-cell-sub">'
        "<strong>0:00:00.0 (1)</strong></small></span>"
    ) in body
    # Only the cell's own text is searched, never a time under it.
    assert table["rows"][0]["search"] == "ann"


def test_a_group_nobody_rode_in_is_left_out():
    columns = [{"id": "name", "label": "Name", "role": "name"}]
    view = rendering.build(
        _document(
            sections=[
                {"title": "M30", "columns": columns, "rows": [{"cells": {"name": "Ann"}}]},
                {"title": "M70+", "columns": columns, "rows": []},
                {"type": "group", "title": "Stage 2", "sections": [{"title": "W", "columns": columns, "rows": []}]},
            ]
        ),
        [],
    )
    assert [s["title"] for s in view["sections"]] == ["M30"]


def test_a_cell_takes_ten_second_lines_and_no_more():
    def cell(n):
        return _raw(sections=[{"columns": [{"id": "a"}], "rows": [{"cells": {"a": {"sub": ["x"] * n}}}]}])

    assert parse(cell(10))
    with pytest.raises(DocumentError, match="at most 10"):
        parse(cell(11))
