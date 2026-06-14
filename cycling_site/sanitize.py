"""Shared HTML sanitizer for submission/API-provided rich-text bodies.

Article bodies (knowledge and news) are stored and rendered as rich HTML, so any
HTML coming from a submission or API call must be reduced to a safe allowlist
before it is saved -- scripts, styles, event handlers and javascript: links are
stripped, while formatting tags (headings, lists, tables, links, emphasis) stay.
"""

from __future__ import annotations

_ALLOWED_BODY_TAGS: frozenset[str] = frozenset(
    {
        "p",
        "br",
        "hr",
        "blockquote",
        "h2",
        "h3",
        "h4",
        "ul",
        "ol",
        "li",
        "strong",
        "b",
        "em",
        "i",
        "code",
        "pre",
        "a",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
    }
)
_ALLOWED_BODY_ATTRS: dict[str, set[str]] = {"a": {"href", "title"}}


def sanitize_rich_html(raw: str) -> str:
    """Reduce arbitrary HTML to the safe rich-text allowlist above."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(raw or "", "html.parser")
    for bad in soup(["script", "style", "iframe", "object", "embed", "form", "link", "meta", "svg"]):
        bad.decompose()
    for tag in soup.find_all(True):
        if tag.name not in _ALLOWED_BODY_TAGS:
            tag.unwrap()
            continue
        allowed = _ALLOWED_BODY_ATTRS.get(tag.name, set())
        for attr in list(tag.attrs):
            if attr.startswith("on") or attr not in allowed:
                del tag[attr]
        if tag.name == "a":
            href_raw = tag.get("href")
            href = href_raw.strip() if isinstance(href_raw, str) else ""
            if href.lower().startswith(("javascript:", "data:", "vbscript:")):
                del tag["href"]
            elif href:
                tag["rel"] = "noopener"
                tag["target"] = "_blank"
    return str(soup).strip()
