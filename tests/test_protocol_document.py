"""The structured protocol document: what it accepts, what it refuses, and what it costs to show."""

import json
from pathlib import Path

import pytest

from protocols import document as doc
from protocols.document import DocumentError, parse

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
