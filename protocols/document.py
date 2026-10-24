"""The structured protocol document, version 1: what the timing software sends instead of (or with)
the HTML it writes for itself.

The document describes itself. It says which sections, columns and cells there are, how each is
labelled and how much each matters; the site knows nothing of laps, attempts, control points,
weather or referees and draws whatever it is given (``rendering.py``). So a protocol gains a column,
a header field or a round of heats by changing the generator only.

Within a major version the site is lenient about what it does not know -- an unknown field is
ignored, an unknown section type is drawn by its shape, an unknown role means no role -- and strict
about what would make the document lie: an id used twice, a cell for a column that does not exist,
a reference to a group or a toggle nobody declared, a link that is not http(s). Breaking changes
raise ``schema``; a document of a major version this site does not know is refused.

Limits bound what one upload can cost to show: the sizes of the parts, and above all the number of
table cells the page has to build -- rows times columns, counted for empty cells too.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, field_validator, model_validator

SCHEMA_VERSION = 1

MAX_TEXT = 2000
MAX_HTML = 20_000
MAX_SUB_LINES = 5
MAX_ITEMS = 50
MAX_GROUPS = 500
MAX_TOGGLES = 20
MAX_SECTIONS = 500
MAX_DEPTH = 3
MAX_COLUMNS = 200
MAX_ROWS_PER_TABLE = 5000
MAX_ROWS = 20_000
#: Rows times columns over every table, plus one per row with a note: what the page has to build.
MAX_CELLS = 100_000

Text = Annotated[str, StringConstraints(max_length=MAX_TEXT)]
Slug = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
Lines = Annotated[list[Text], Field(max_length=MAX_SUB_LINES)]


class DocumentError(ValueError):
    """The document cannot be accepted; the message says why, for the generator's log."""


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Item(_Lenient):
    """A line of the header or the footer: a labelled field, a plain line, or sanitized HTML."""

    type: Text = "field"
    key: Annotated[str, StringConstraints(pattern=r"^[a-z0-9_-]{1,40}$")] | None = None
    label: Text | None = None
    value: Text | None = None
    text: Text | None = None
    html: Annotated[str, StringConstraints(max_length=MAX_HTML)] | None = None


class CellObject(_Lenient):
    text: Text = ""
    sub: Lines = []
    url: Text | None = None
    strong: bool = False

    @field_validator("url")
    @classmethod
    def _http_only(cls, url: str | None) -> str | None:
        if url is not None and not url.lower().startswith(("http://", "https://")):
            raise ValueError("a link must be http or https")
        return url


Cell = Text | CellObject


class Column(_Lenient):
    id: Slug
    label: Text = ""
    sub_label: Lines = []
    group: Text | None = None
    role: Text | None = None
    priority: Annotated[int, Field(ge=1, le=3)] | None = None
    toggle: Slug | None = None
    align: Text | None = None


class Row(_Lenient):
    cells: dict[str, Cell] = {}
    group: Annotated[str, StringConstraints(min_length=1, max_length=100)] | None = None
    status: Text | None = None
    note: Text | None = None


class Section(_Lenient):
    type: Text = "table"
    title: Text | None = None
    group: Annotated[str, StringConstraints(min_length=1, max_length=100)] | None = None
    columns: list[Column] = []
    rows: list[Row] = []
    sections: list[Section] = []


class Group(_Lenient):
    id: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    label: Text = ""


class Toggle(_Lenient):
    id: Slug
    label: Text = ""
    default: bool = True


class Generator(_Lenient):
    name: Text = ""
    version: Text = ""


class Document(_Lenient):
    schema_: int = Field(alias="schema")
    lang: Annotated[str, StringConstraints(pattern=r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$")] | None = None
    title: Text | None = None
    generator: Generator | None = None
    header: Annotated[list[Item], Field(max_length=MAX_ITEMS)] = []
    groups: Annotated[list[Group], Field(max_length=MAX_GROUPS)] = []
    toggles: Annotated[list[Toggle], Field(max_length=MAX_TOGGLES)] = []
    sections: list[Section]
    footer: Annotated[list[Item], Field(max_length=MAX_ITEMS)] = []

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    @model_validator(mode="after")
    def _consistent(self) -> Document:
        _unique([g.id for g in self.groups], "group")
        _unique([t.id for t in self.toggles], "toggle")
        groups = {g.id for g in self.groups}
        toggles = {t.id for t in self.toggles}
        totals = {"sections": 0, "rows": 0, "cells": 0}
        for section in self.sections:
            _check_section(section, 1, groups, toggles, totals)
        if totals["sections"] > MAX_SECTIONS:
            raise ValueError(f"too many sections ({totals['sections']} > {MAX_SECTIONS})")
        if totals["rows"] > MAX_ROWS:
            raise ValueError(f"too many rows ({totals['rows']} > {MAX_ROWS})")
        if totals["cells"] > MAX_CELLS:
            raise ValueError(
                f"the tables are too big to show: {totals['cells']} cells (rows x columns, plus notes) > {MAX_CELLS}"
            )
        return self


def _unique(ids: list[str], what: str) -> None:
    seen: set[str] = set()
    for value in ids:
        if value in seen:
            raise ValueError(f"{what} id {value!r} is used twice")
        seen.add(value)


def _check_section(section: Section, depth: int, groups: set[str], toggles: set[str], totals: dict) -> None:
    if depth > MAX_DEPTH:
        raise ValueError(f"sections are nested deeper than {MAX_DEPTH}")
    totals["sections"] += 1
    if section.group is not None and section.group not in groups:
        raise ValueError(f"section group {section.group!r} is not in the groups list")
    _check_table(section, groups, toggles, totals)
    for child in section.sections:
        _check_section(child, depth + 1, groups, toggles, totals)


def _check_table(section: Section, groups: set[str], toggles: set[str], totals: dict) -> None:
    if len(section.columns) > MAX_COLUMNS:
        raise ValueError(f"a table has too many columns ({len(section.columns)} > {MAX_COLUMNS})")
    if len(section.rows) > MAX_ROWS_PER_TABLE:
        raise ValueError(f"a table has too many rows ({len(section.rows)} > {MAX_ROWS_PER_TABLE})")
    ids = [c.id for c in section.columns]
    _unique(ids, "column")
    for column in section.columns:
        if column.toggle is not None and column.toggle not in toggles:
            raise ValueError(f"column {column.id!r} names toggle {column.toggle!r}, which is not in the toggles list")
    known = set(ids)
    for row in section.rows:
        stray = set(row.cells) - known
        if stray:
            raise ValueError(f"a row has cells for columns that do not exist: {sorted(stray)}")
        if row.group is not None and row.group not in groups:
            raise ValueError(f"row group {row.group!r} is not in the groups list")
        if row.note:
            totals["cells"] += 1
    totals["rows"] += len(section.rows)
    totals["cells"] += len(section.rows) * len(section.columns)


def _too_deep(sections: Any) -> bool:
    """Whether sections nest deeper than allowed -- checked before the recursive models
    see them, so a deep document is refused with a short reason, not a long trace."""
    stack = [(sections, 1)]
    while stack:
        items, depth = stack.pop()
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and item.get("sections"):
                if depth >= MAX_DEPTH:
                    return True
                stack.append((item["sections"], depth + 1))
    return False


def parse(raw: bytes) -> dict:
    """The accepted document as it is stored, or DocumentError saying what is wrong with it."""
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, RecursionError) as exc:
        # ValueError covers bad UTF-8 and JSON and also numbers too long to convert;
        # RecursionError, arrays nested deeper than Python follows.
        raise DocumentError(f"The document is not UTF-8 JSON: {exc}") from None
    if not isinstance(data, dict):
        raise DocumentError("The document must be a JSON object")
    version = data.get("schema")
    if version != SCHEMA_VERSION:
        raise DocumentError(f"Unsupported protocol document schema {version!r}; this site supports {SCHEMA_VERSION}")
    if _too_deep(data.get("sections")):
        raise DocumentError(f"Sections are nested deeper than {MAX_DEPTH}")
    try:
        document = Document.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(p) for p in error['loc'])}: {error['msg']}" for error in exc.errors()[:5])
        raise DocumentError(f"The document does not match schema {SCHEMA_VERSION}: {problems}") from None
    return document.model_dump(mode="json", by_alias=True, exclude_none=True)


def json_schema() -> dict[str, Any]:
    """The JSON Schema the generators check their documents against (exported to schema/)."""
    return Document.model_json_schema(by_alias=True)
