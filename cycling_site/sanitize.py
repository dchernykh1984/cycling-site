"""Shared HTML sanitizer for submission/API-provided rich-text bodies.

Article bodies (knowledge and news) and competition descriptions are stored and
rendered as rich HTML, so any HTML coming from a submission or API call must be
reduced to a safe allowlist before it is saved -- scripts, styles, event handlers
and javascript: links are stripped, while formatting tags (headings, lists, tables,
links, emphasis) stay. Pass ``allow_img=True`` to additionally permit images with a
safe ``src`` (used by competition descriptions).
"""

from __future__ import annotations

import re

from django.utils.html import urlize

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
_IMG_ATTRS: set[str] = {"src", "alt"}
# Only http(s) URLs or base64-encoded raster data URIs -- never javascript:, vbscript:,
# data:text/html or data:image/svg+xml (SVG can carry script).
_SAFE_IMG_SRC = re.compile(r"^(?:https?://|data:image/(?:png|jpe?g|gif|webp)[;,])", re.IGNORECASE)


def _clean_attrs_and_links(tag) -> bool:
    """Strip disallowed attrs and normalize <a>/<img>; return False if the tag must be dropped."""
    allowed = _IMG_ATTRS if tag.name == "img" else _ALLOWED_BODY_ATTRS.get(tag.name, set())
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
    elif tag.name == "img":
        src_raw = tag.get("src")
        src = src_raw.strip() if isinstance(src_raw, str) else ""
        if not _SAFE_IMG_SRC.match(src):
            return False  # an image without a safe src is useless -- drop it
    return True


def sanitize_rich_html(raw: str, *, allow_img: bool = False) -> str:
    """Reduce arbitrary HTML to the safe rich-text allowlist above.

    When ``allow_img`` is true, ``<img>`` tags with a safe ``src`` (http(s) or a base64
    raster data URI) are kept; everything else stays on the text-formatting allowlist.
    """
    from bs4 import BeautifulSoup

    allowed_tags = _ALLOWED_BODY_TAGS | ({"img"} if allow_img else frozenset())
    soup = BeautifulSoup(raw or "", "html.parser")
    for bad in soup(["script", "style", "iframe", "object", "embed", "form", "link", "meta", "svg"]):
        bad.decompose()
    for tag in soup.find_all(True):
        if tag.name not in allowed_tags:
            tag.unwrap()
        elif not _clean_attrs_and_links(tag):
            tag.decompose()
    return str(soup).strip()


def plaintext_to_html(text: str) -> str:
    """Convert a plain-text string to safe HTML.

    Escapes the text, turns bare URLs into links that open in a new tab, and preserves
    paragraphs / line breaks. Used to migrate existing plain-text descriptions to the
    HTML rendering and as the canonical "plain text -> safe html" conversion.
    """
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    html = urlize(normalized, nofollow=False, autoescape=True)  # escapes text + linkifies URLs
    html = html.replace("<a ", '<a target="_blank" rel="noopener noreferrer nofollow" ')
    paragraphs = [p for p in re.split(r"\n{2,}", html) if p.strip()]
    return "".join("<p>" + p.replace("\n", "<br>") + "</p>" for p in paragraphs)
