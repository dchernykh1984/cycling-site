"""Turn a stored protocol document into what the templates draw.

Everything the page needs is worked out here, once, so the templates only lay it out: each column's
effective priority, the header groups above the columns, every cell in column order, the text the
search looks in, the group a row belongs to. The document says what the data is; how much of it a
phone shows, and how, is decided here and in protocol.css / protocol-doc.js.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from django.utils.html import escape
from django.utils.safestring import SafeString, mark_safe
from django.utils.translation import get_language, get_language_info, gettext

from cycling_site.sanitize import sanitize_rich_html
from cycling_site.text_search import fold_table, search_words

#: Columns that stay on a phone even when the document gives them no priority.
_PRIMARY_ROLES = frozenset({"place", "bib", "name", "result"})
#: A time, a gap or a pace ("1:23:45.6", "+0:12"): left out of the search, so a bib number finds
#: its rider rather than everyone whose time contains those digits.
_TIME = re.compile(r"^[+-]?\(?\d+(?::\d{1,2})+(?:[.,]\d+)?\)?$")
#: How many leading columns stand in for priority 1 when a table has none.
_FALLBACK_PRIMARY = 3
_ALIGNS = frozenset({"start", "center", "end"})
_KNOWN_ROLES = frozenset({"place", "bib", "name", "result", "gap", "group", "team"})
_CSS_WORD = re.compile(r"[^a-z0-9_-]")


_KNOWN_STATUSES = frozenset({"ok", "dnf", "dns", "dsq"})


def _status_class(status: str | None) -> str:
    """A row's status as a class: a known one, or "other" -- never an arbitrary string."""
    if not status:
        return ""
    word = _css_word(status)
    return word if word in _KNOWN_STATUSES else "other"


def _css_word(value: str | None) -> str:
    return _CSS_WORD.sub("", (value or "").lower()) or "other"


def _cell(raw) -> dict:
    if isinstance(raw, str):
        return {"text": raw, "sub": [], "url": "", "strong": False}
    if isinstance(raw, dict):
        return {
            "text": raw.get("text", ""),
            "sub": raw.get("sub", []),
            "url": raw.get("url", ""),
            "strong": bool(raw.get("strong")),
        }
    return {"text": "", "sub": [], "url": "", "strong": False}


def _cell_text(cell: dict) -> str:
    return " ".join([cell["text"], *cell["sub"]]).strip()


def _columns(raw_columns: list[dict], off_toggles: frozenset[str] = frozenset()) -> list[dict]:
    columns = []
    for index, raw in enumerate(raw_columns):
        role = raw.get("role") or ""
        priority = raw.get("priority") or (1 if role in _PRIMARY_ROLES else 2)
        align = raw.get("align") if raw.get("align") in _ALIGNS else ""
        columns.append(
            {
                "index": index,
                "id": raw["id"],
                "label": raw.get("label", ""),
                "sub_label": raw.get("sub_label", []),
                "group": raw.get("group"),
                "role": role,
                # Only the roles the site knows become a class: a cell carries it once per
                # row, so an arbitrary role would be repeated through the whole table.
                "role_class": role if role in _KNOWN_ROLES else "",
                "priority": priority,
                "toggle": raw.get("toggle") or "",
                "align": align,
            }
        )
    if columns and not any(c["priority"] == 1 for c in columns):
        # A table must never be empty on a phone: its first columns shown at opening stand
        # in. Which columns are on can change later -- protocol-doc.js keeps the same rule.
        for column in [c for c in columns if c["toggle"] not in off_toggles][:_FALLBACK_PRIMARY]:
            column["priority"] = 1
    return columns


def _header_groups(columns: list[dict]) -> list[dict]:
    """Runs of neighbouring columns sharing a group label, one header cell each; None if no groups."""
    if not any(c["group"] for c in columns):
        return []
    runs: list[dict] = []
    for column in columns:
        label = column["group"] or ""
        if runs and label and runs[-1]["label"] == label:
            runs[-1]["columns"].append(column["index"])
        else:
            runs.append({"label": label, "columns": [column["index"]]})
    for run in runs:
        run["colspan"] = len(run["columns"])
        run["cols"] = " ".join(str(i) for i in run["columns"])
    return runs


def _has_content(column: dict, rows: list[dict]) -> bool:
    """A column with no heading and nothing in any row draws only an unnamed, empty band."""
    if column.get("label") or column.get("sub_label") or not rows:
        return True
    return any(row.get("cells", {}).get(column["id"]) for row in rows)


def _table(raw: dict, inherited_group: str | None, counter: list[int], off_toggles: frozenset[str]) -> dict:
    raw_rows = raw.get("rows", [])
    columns = _columns([c for c in raw.get("columns", []) if _has_content(c, raw_rows)], off_toggles)
    rows = []
    for raw_row in raw.get("rows", []):
        counter[0] += 1
        cells_raw = raw_row.get("cells", {})
        cells = [_cell(cells_raw.get(c["id"], "")) for c in columns]
        rows.append(
            {
                "number": counter[0],
                "cells": list(zip(columns, cells, strict=True)),
                "group": raw_row.get("group") or inherited_group or "",
                "status": _status_class(raw_row.get("status")),
                "note": [line for line in (raw_row.get("note") or "").split("\n") if line],
                # Folded like the query (protocol-doc.js, with fold_table), so either script finds either.
                "search": " ".join(search_words(" ".join(c["text"] for c in cells if not _TIME.match(c["text"])))),
                "who": " ".join(_cell_text(cells[c["index"]]) for c in columns if c["role"] in ("bib", "name")).strip(),
            }
        )
    width = len(columns) + 1  # the column of row buttons
    return {
        "columns": columns,
        "header_groups": _header_groups(columns),
        "rows": rows,
        "body": _body_html(columns, rows, width),
        "width": width,
    }


def _column_attrs(column: dict) -> str:
    classes = f"prio-{column['priority']}"
    if column["role_class"]:
        classes += f" role-{column['role_class']}"
    if column["align"]:
        classes += f" align-{column['align']}"
    # The label is kept once, on the column's heading (protocol-doc.js reads it there):
    # repeated in every cell, a long label would multiply the page by the row count.
    attrs = f' class="{classes}" data-col="{column["index"]}"'
    if column["toggle"]:
        attrs += f' data-toggle-id="{escape(column["toggle"])}"'
    return attrs


def _cell_html(cell: dict) -> str:
    text: str = escape(cell["text"])
    if cell["strong"]:
        text = f"<strong>{text}</strong>"
    if cell["url"]:
        text = f'<a href="{escape(cell["url"])}" rel="nofollow noopener" target="_blank">{text}</a>'
    return text + "".join(f'<br><small class="protocol-cell-sub">{escape(line)}</small>' for line in cell["sub"])


def _body_html(columns: list[dict], rows: list[dict], width: int) -> SafeString:
    """The table's rows as markup, built here rather than in a template loop.

    A table may hold tens of thousands of cells (FR-PRO-008); a template tag per cell costs seconds
    at that size, string joining a fraction of one. Every value is escaped on the way in.
    """
    attrs = [_column_attrs(c) for c in columns]
    details = gettext("Details")
    parts = []
    for row in rows:
        number = row["number"]
        status = f" status-{row['status']}" if row["status"] else ""
        group = f' data-group-id="{escape(row["group"])}"' if row["group"] else ""
        label = escape(f"{details}: {row['who']}" if row["who"] else details)
        parts.append(
            f'<tr class="protocol-row{status}" id="row-{number}" data-search="{escape(row["search"])}"{group}>'
            f'<td class="protocol-expand-col"><button type="button" class="protocol-row-expand" aria-expanded="false"'
            f' aria-controls="row-{number}-details" aria-label="{label}" hidden><span aria-hidden="true">+</span>'
            "</button></td>"
        )
        parts.extend(
            f"<td{attr}>{_cell_html(cell)}</td>" for attr, (_column, cell) in zip(attrs, row["cells"], strict=True)
        )
        parts.append("</tr>")
        if row["note"]:
            note = "<br>".join(escape(line) for line in row["note"])
            parts.append(f'<tr class="protocol-note" data-for="row-{number}"><td colspan="{width}">{note}</td></tr>')
    return mark_safe("".join(parts))  # noqa: S308 -- every value above went through escape()


def _sections(
    raw_sections: list[dict], inherited_group: str | None, prefix: str, counter: list[int], off_toggles: frozenset[str]
) -> list:
    sections = []
    for number, raw in enumerate(raw_sections, start=1):
        anchor = f"{prefix}-{number}"
        group = raw.get("group") or inherited_group
        section = {
            "anchor": anchor,
            "title": raw.get("title", ""),
            "table": _table(raw, group, counter, off_toggles) if raw.get("columns") else None,
            "sections": _sections(raw.get("sections", []), group, anchor, counter, off_toggles),
        }
        sections.append(section)
    return sections


def _own_images_only(html: str, sources: list[str]) -> str:
    """A protocol is somebody else's markup: its pictures may come only from this site or inline."""
    soup = BeautifulSoup(html, "html.parser")
    origins = {urlsplit(s)._replace(path="", query="", fragment="").geturl() for s in sources}
    for img in soup.find_all("img"):
        src = str(img.get("src", ""))
        if src.startswith("data:"):
            continue
        try:
            parts = urlsplit(src)
        except ValueError:  # an address no browser could load either
            img.decompose()
            continue
        if f"{parts.scheme}://{parts.netloc}" not in origins:
            img.decompose()
    return str(soup)


def _items(raw_items: list[dict], sources: list[str]) -> list[dict]:
    items = []
    for raw in raw_items:
        kind = raw.get("type", "field")
        if kind == "html" and raw.get("html"):
            items.append(
                {"kind": "html", "html": _own_images_only(sanitize_rich_html(raw["html"], allow_img=True), sources)}
            )
        elif kind == "field" and raw.get("value"):
            items.append(
                {"kind": "field", "key": raw.get("key", ""), "label": raw.get("label", ""), "value": raw["value"]}
            )
        elif raw.get("text") or raw.get("value"):
            items.append({"kind": "text", "text": raw.get("text") or raw.get("value") or ""})
    return items


def _language_note(lang: str | None) -> str:
    """The protocol's language when it differs from the page's, named in its own words."""
    if not lang:
        return ""
    base = lang.split("-")[0]
    if base == (get_language() or "").split("-")[0]:
        return ""
    try:
        return get_language_info(base)["name_local"]
    except KeyError:
        return lang


def build(document: dict, image_sources: list[str]) -> dict:
    """Everything the protocol templates draw, from a stored document."""
    counter = [0]
    off_toggles = frozenset(t["id"] for t in document.get("toggles", []) if not t.get("default", True))
    return {
        "title": document.get("title", ""),
        "lang": document.get("lang", ""),
        "language_note": _language_note(document.get("lang")),
        "header": _items(document.get("header", []), image_sources),
        "footer": _items(document.get("footer", []), image_sources),
        "groups": document.get("groups", []),
        "toggles": document.get("toggles", []),
        "sections": _sections(document.get("sections", []), None, "sec", counter, off_toggles),
        "fold": json.dumps(fold_table()),
    }
