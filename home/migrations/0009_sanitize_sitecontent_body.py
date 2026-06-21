import re

from django.db import migrations

# Self-contained snapshot of the rich-text sanitizer (frozen at the time this migration was
# written). A data migration must be reproducible from its own code, so it does NOT import the
# live cycling_site.sanitize helper, which may be renamed or change its allowlist later. This
# mirrors sanitize_rich_html(allow_img=True), the policy SiteContent.save() applies.
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
_IMG_ATTRS = {"src", "alt"}
_SAFE_IMG_SRC = re.compile(r"^(?:https?://|data:image/(?:png|jpe?g|gif|webp)[;,])", re.IGNORECASE)
_ALLOWED_LINK_SCHEMES = ("http", "https", "mailto", "tel")
_URL_STRIP_CHARS = re.compile(r"[\x00-\x20\x7f]")


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


def _clean_tag(tag):
    allowed = _IMG_ATTRS if tag.name == "img" else (_A_ATTRS if tag.name == "a" else set())
    for attr in list(tag.attrs):
        if attr.startswith("on") or attr not in allowed:
            del tag[attr]
    if tag.name == "a":
        href = _safe_href(tag.get("href"))
        if href is None:
            del tag["href"]
        else:
            tag["href"], tag["rel"], tag["target"] = href, "noopener", "_blank"
    elif tag.name == "img":
        src_raw = tag.get("src")
        src = src_raw.strip() if isinstance(src_raw, str) else ""
        if not _SAFE_IMG_SRC.match(src):
            return False
    return True


def _sanitize(raw):
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(raw or "", "html.parser")
    for bad in soup(["script", "style", "iframe", "object", "embed", "form", "link", "meta", "svg"]):
        bad.decompose()
    for tag in soup.find_all(True):
        if tag.name not in _ALLOWED_TAGS:
            tag.unwrap()
        elif not _clean_tag(tag):
            tag.decompose()
    return str(soup).strip()


_BODY_FIELDS = ("body", "body_ru", "body_kk", "body_en")


def sanitize_existing_body(apps, schema_editor):
    """Backfill: clean SiteContent body columns rendered via |safe on the home page, so HTML
    stored before save()-time sanitization existed can't remain an active stored XSS. Idempotent;
    a no-op on a fresh database.
    """
    SiteContent = apps.get_model("home", "SiteContent")
    for obj in SiteContent.objects.all():
        changed = []
        for field in _BODY_FIELDS:
            value = getattr(obj, field, None)
            if value:
                cleaned = _sanitize(value)
                if cleaned != value:
                    setattr(obj, field, cleaned)
                    changed.append(field)
        if changed:
            obj.save(update_fields=changed)


class Migration(migrations.Migration):
    dependencies = [
        ("home", "0008_fix_wagtail_site_hostname"),
    ]

    operations = [
        migrations.RunPython(sanitize_existing_body, migrations.RunPython.noop),
    ]
