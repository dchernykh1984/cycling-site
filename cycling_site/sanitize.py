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
        "u",
        "s",
        "sub",
        "sup",
        "span",
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
# On <img>: the alt text and safe src, plus the geometry the editor's image tool (blot-formatter)
# writes -- numeric width/height and a data-align keyword; the inline float/margin it also writes
# is handled by the style allowlist below.
_IMG_ATTRS: set[str] = {"src", "alt", "width", "height", "data-align"}
_ALIGN_KEYWORDS = frozenset({"left", "right", "center"})
# A non-negative CSS length for a width/height *attribute* (bare number = px, or px/%).
_DIMENSION = re.compile(r"^\d+(?:\.\d+)?(?:px|%)?$")
# Only http(s) URLs or base64-encoded raster data URIs -- never javascript:, vbscript:,
# data:text/html or data:image/svg+xml (SVG can carry script).
_SAFE_IMG_SRC = re.compile(r"^(?:https?://|data:image/(?:png|jpe?g|gif|webp)[;,])", re.IGNORECASE)
# Schemes allowed in <a href>; everything else (javascript:, data:, vbscript:, ...) is dropped.
_ALLOWED_LINK_SCHEMES = ("http", "https", "mailto", "tel")
# ASCII control chars + whitespace that browsers strip when resolving a URL (and which
# BeautifulSoup produces when decoding entities like &#x0a;), so they cannot be used to
# smuggle "java\nscript:" past a naive prefix check.
_URL_STRIP_CHARS = re.compile(r"[\x00-\x20\x7f]")


def _safe_href(href_raw: object) -> str | None:
    """Return a control-char-stripped href if its scheme is safe, else None to drop it.

    Browsers ignore ASCII control/whitespace characters when parsing a URL's scheme, so a
    value such as ``java&#x0a;script:alert(1)`` (entity-decoded to ``java\\nscript:...`` by
    the parser) would slip past a plain ``startswith("javascript:")`` check yet still run.
    Strip those characters first, then allow an explicit scheme only if it is on the
    allowlist; URLs with no scheme (relative, anchor, query) are kept.
    """
    if not isinstance(href_raw, str):
        return None
    cleaned = _URL_STRIP_CHARS.sub("", href_raw)
    if not cleaned:
        return None
    for ch in cleaned:
        if ch == ":":
            scheme = cleaned.split(":", 1)[0].lower()
            return cleaned if scheme in _ALLOWED_LINK_SCHEMES else None
        if ch in "/?#":
            break  # a path/query/fragment delimiter before any ':' -> no scheme, relative URL
    return cleaned


# CSS classes kept on any tag: only Quill's block alignment / indentation classes. They carry
# no behaviour, just layout, and are rendered on public article pages by cycling_site.css
# (Quill's own CSS is editor-only). Every other class is dropped.
_ALLOWED_CLASSES = frozenset(
    {"ql-align-left", "ql-align-center", "ql-align-right", "ql-align-justify"}
    | {f"ql-indent-{level}" for level in range(1, 9)}
)
# Inline style is permitted only on <span> (text colour, from the colour picker) and <img>
# (size + float, from the image tool), and only for these properties with a strictly validated
# value -- so url()/expression()/scripts can never ride in on a style attribute.
_UNSAFE_STYLE = re.compile(r"url\(|expression|javascript|/\*|\\|[<>]", re.IGNORECASE)
_LENGTH = re.compile(r"^-?\d+(?:\.\d+)?(?:px|%|em|rem)$|^0$")
_COLOR = re.compile(r"^#[0-9a-fA-F]{3,8}$|^rgba?\(\s*[\d.,%\s]+\)$", re.IGNORECASE)


def _is_length(value: str) -> bool:
    return bool(_LENGTH.match(value.strip()))


def _is_length_or_auto(value: str) -> bool:
    return value.strip() == "auto" or _is_length(value)


def _is_margin(value: str) -> bool:
    parts = value.split()
    return 1 <= len(parts) <= 4 and all(_is_length_or_auto(part) for part in parts)


def _is_color(value: str) -> bool:
    return bool(_COLOR.match(value.strip()))


_SPAN_STYLE = {"color": _is_color, "background-color": _is_color}
_IMG_STYLE = {
    "width": _is_length,
    "height": _is_length,
    "max-width": _is_length,
    "float": lambda v: v.strip().lower() in {"left", "right", "none"},
    "display": lambda v: v.strip().lower() in {"block", "inline", "inline-block"},
    "margin": _is_margin,
    "margin-left": _is_length_or_auto,
    "margin-right": _is_length_or_auto,
    "margin-top": _is_length,
    "margin-bottom": _is_length,
}


def _sanitize_class(value: object) -> list[str]:
    """Return the allowlisted CSS classes present on ``value`` (possibly empty)."""
    classes = value if isinstance(value, list) else str(value or "").split()
    return [cls for cls in classes if cls in _ALLOWED_CLASSES]


def _sanitize_style(value: object, allowed: dict) -> str:
    """Keep only allowlisted ``prop: value`` declarations with a validated value.

    Returns the rebuilt style string ("" if nothing survives). A value containing url(),
    expression(), an escape or angle brackets drops the whole attribute -- no safe declaration
    needs them, and they are the vectors a style attribute could smuggle a fetch/script through.
    """
    if not isinstance(value, str) or _UNSAFE_STYLE.search(value):
        return ""
    kept = []
    for declaration in value.split(";"):
        prop, sep, raw = declaration.partition(":")
        if not sep:
            continue
        prop, raw = prop.strip().lower(), raw.strip()
        validator = allowed.get(prop)
        if raw and validator is not None and validator(raw):
            kept.append(f"{prop}: {raw}")
    return "; ".join(kept)


def _keep_only(tag, allowed: set) -> None:
    """Drop every attribute not in ``allowed`` (and any ``on*`` handler)."""
    for attr in list(tag.attrs):
        if attr.startswith("on") or attr not in allowed:
            del tag[attr]


def _apply_class_and_style(tag, style_allowed: dict | None) -> None:
    """Reduce the tag's ``class`` to the allowlist and its ``style`` to ``style_allowed``."""
    classes = _sanitize_class(tag.get("class"))
    if classes:
        tag["class"] = classes
    else:
        del tag["class"]
    style = _sanitize_style(tag.get("style"), style_allowed) if style_allowed is not None else ""
    if style:
        tag["style"] = style
    else:
        del tag["style"]


def _clean_attrs_and_links(tag) -> bool:
    """Strip disallowed attrs and normalize <a>/<img>; return False if the tag must be dropped."""
    name = tag.name
    if name == "img":
        src_raw = tag.get("src")
        src = src_raw.strip() if isinstance(src_raw, str) else ""
        if not _SAFE_IMG_SRC.match(src):
            return False  # an image without a safe src is useless -- drop it
        _keep_only(tag, _IMG_ATTRS | {"class", "style"})
        tag["src"] = src
        for dimension in ("width", "height"):
            if tag.has_attr(dimension) and not _DIMENSION.match(str(tag[dimension]).strip()):
                del tag[dimension]
        if tag.has_attr("data-align") and str(tag["data-align"]).strip().lower() not in _ALIGN_KEYWORDS:
            del tag["data-align"]
        _apply_class_and_style(tag, _IMG_STYLE)
        return True
    if name == "a":
        _keep_only(tag, _ALLOWED_BODY_ATTRS["a"] | {"class"})
        href = _safe_href(tag.get("href"))
        if href is None:
            del tag["href"]
        else:
            tag["href"] = href
            tag["rel"] = "noopener"
            tag["target"] = "_blank"
        _apply_class_and_style(tag, None)
        return True
    style_allowed = _SPAN_STYLE if name == "span" else None
    _keep_only(tag, _ALLOWED_BODY_ATTRS.get(name, set()) | {"class"} | ({"style"} if style_allowed else set()))
    _apply_class_and_style(tag, style_allowed)
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


def sanitize_rich_text_columns(instance, fields, *, update_fields=None) -> None:
    """Sanitize the given rich-text columns of a model instance in place, for use in ``save()``.

    The single choke point for models whose rich-text body/description is rendered with
    ``|safe`` (competitions, news, the home page). Columns are read/written via ``__dict__`` so
    modeltranslation's canonical descriptor is not tripped -- the canonical column and the
    per-locale ``*_ru/_kk/_en`` columns are all plain ``__dict__`` entries. A no-op when an
    ``update_fields`` save touches none of them; ``sanitize_rich_html`` is idempotent, so
    re-saving an already-clean value is safe.
    """
    if update_fields is not None and not any(field in update_fields for field in fields):
        return
    for field in fields:
        value = instance.__dict__.get(field)
        if value:
            instance.__dict__[field] = sanitize_rich_html(value, allow_img=True)


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
