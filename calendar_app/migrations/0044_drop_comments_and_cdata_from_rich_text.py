import re

from django.db import migrations

# Self-contained copy of cycling_site.sanitize.sanitize_rich_html(allow_img=True), the policy every
# rich-text save() applies, as it stands once it drops comments, CDATA, doctypes and processing
# instructions. Frozen here, as in 0013 and home 0009: a data migration must not change when the live
# helper does.
_ALLOWED_TAGS = frozenset(
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
        "img",
    }
)
_A_ATTRS = {"href", "title"}
_IMG_ATTRS = {"src", "alt", "width", "height", "data-align"}
_ALIGN_KEYWORDS = frozenset({"left", "right", "center"})
_DIMENSION = re.compile(r"^\d+(?:\.\d+)?(?:px|%)?$")
_SAFE_IMG_SRC = re.compile(r"^(?:https?://|data:image/(?:png|jpe?g|gif|webp)[;,])", re.IGNORECASE)
_ALLOWED_LINK_SCHEMES = ("http", "https", "mailto", "tel")
_URL_STRIP_CHARS = re.compile(r"[\x00-\x20\x7f]")
_ALLOWED_CLASSES = frozenset(
    {"ql-align-left", "ql-align-center", "ql-align-right", "ql-align-justify"}
    | {f"ql-indent-{level}" for level in range(1, 9)}
)
_UNSAFE_STYLE = re.compile(r"url\(|expression|javascript|/\*|\\|[<>]", re.IGNORECASE)
_LENGTH = re.compile(r"^-?\d+(?:\.\d+)?(?:px|%|em|rem)$|^0$")
_COLOR = re.compile(r"^#[0-9a-fA-F]{3,8}$|^rgba?\([\d.,%\s]+\)$", re.IGNORECASE)


def _safe_href(href_raw):
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
            break
    return cleaned


def _is_length(value):
    return bool(_LENGTH.match(value.strip()))


def _is_length_or_auto(value):
    return value.strip() == "auto" or _is_length(value)


def _is_margin(value):
    parts = value.split()
    return 1 <= len(parts) <= 4 and all(_is_length_or_auto(part) for part in parts)


def _is_color(value):
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


def _sanitize_style(value, allowed):
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


def _keep_only(tag, allowed):
    for attr in list(tag.attrs):
        if attr.startswith("on") or attr not in allowed:
            del tag[attr]


def _apply_class_and_style(tag, style_allowed):
    value = tag.get("class")
    classes = [
        cls for cls in (value if isinstance(value, list) else str(value or "").split()) if cls in _ALLOWED_CLASSES
    ]
    if classes:
        tag["class"] = classes
    else:
        del tag["class"]
    style = _sanitize_style(tag.get("style"), style_allowed) if style_allowed is not None else ""
    if style:
        tag["style"] = style
    else:
        del tag["style"]


def _clean_attrs_and_links(tag):
    name = tag.name
    if name == "img":
        src_raw = tag.get("src")
        src = src_raw.strip() if isinstance(src_raw, str) else ""
        if not _SAFE_IMG_SRC.match(src):
            return False
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
        _keep_only(tag, _A_ATTRS | {"class"})
        href = _safe_href(tag.get("href"))
        if href is None:
            del tag["href"]
        else:
            tag["href"] = href
            if not href.startswith("#"):
                tag["rel"] = "noopener"
                tag["target"] = "_blank"
        _apply_class_and_style(tag, None)
        return True
    style_allowed = _SPAN_STYLE if name == "span" else None
    _keep_only(tag, {"class"} | ({"style"} if style_allowed else set()))
    _apply_class_and_style(tag, style_allowed)
    return True


def _sanitize(raw):
    from bs4 import BeautifulSoup
    from bs4.element import PreformattedString

    soup = BeautifulSoup(raw or "", "html.parser")
    for parent in [soup, *soup.find_all(True)]:
        for index in range(len(parent.contents) - 1, -1, -1):
            if isinstance(parent.contents[index], PreformattedString):
                parent.contents[index].extract(_self_index=index)
    for bad in soup(["script", "style", "iframe", "object", "embed", "form", "link", "meta", "svg"]):
        bad.decompose()
    for tag in soup.find_all(True):
        if tag.name not in _ALLOWED_TAGS:
            tag.hidden = True
        elif not _clean_attrs_and_links(tag):
            tag.decompose()
    return str(soup).strip()


# The rich text drawn with |safe that only save() cleans. A protocol document's HTML is cleaned at
# every draw, so the stored ones need nothing.
_COLUMNS = (
    ("calendar_app", "Competition", ("description", "description_ru", "description_kk", "description_en")),
    ("news", "NewsArticle", ("body", "body_ru", "body_kk", "body_en")),
    ("knowledge", "KnowledgeArticle", ("body",)),
    ("home", "HomeCard", ("body", "body_ru", "body_kk", "body_en")),
)


def drop_comments_and_cdata(apps, schema_editor):
    """Clean the rich text saved before the sanitizer dropped comments and CDATA, once.

    A browser may end such a node at its first ">", where the sanitizer read on and so left the rest
    unchecked: "<![CDATA[><img onerror=...>]]>" ran the handler. Only a text holding "<!" or "<?" is
    touched -- the sanitizer writes every other "<" as "&lt;", so no other text holds one of these
    nodes -- and every other keeps its bytes, though an older save wrote some of them otherwise.
    A no-op on a fresh database.
    """
    for app_label, model_name, fields in _COLUMNS:
        model = apps.get_model(app_label, model_name)
        for row in model.objects.iterator():
            cleaned = {
                field: _sanitize(value)
                for field in fields
                if (value := getattr(row, field)) and ("<!" in value or "<?" in value)
            }
            if cleaned:
                model.objects.filter(pk=row.pk).update(**cleaned)


class Migration(migrations.Migration):
    dependencies = [
        ("calendar_app", "0043_add_lecture_and_workshop_event_types"),
        ("home", "0011_remove_sitecontent_body"),
        ("knowledge", "0012_knowledgearticlecomment"),
        ("news", "0005_newsarticlecomment"),
    ]

    operations = [
        migrations.RunPython(drop_comments_and_cdata, migrations.RunPython.noop),
    ]
