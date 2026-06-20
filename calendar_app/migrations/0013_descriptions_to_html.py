import re

from django.db import migrations
from django.utils.html import urlize

_FIELDS = ("description", "description_ru", "description_kk", "description_en")


def _plain_to_html(text: str) -> str:
    """Plain text -> safe HTML: escape, linkify URLs (new tab), keep paragraphs.

    Self-contained (no app-code import, so the conversion is frozen for this migration)
    and *always* escapes via urlize(autoescape=True), so no value is ever passed through
    as raw HTML -- a historical description containing e.g. ``<script>`` becomes inert
    escaped text rather than stored XSS. Existing descriptions are plain text at the time
    this migration runs.
    """
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    html = urlize(normalized, nofollow=False, autoescape=True)
    html = html.replace("<a ", '<a target="_blank" rel="noopener noreferrer nofollow" ')
    paragraphs = [p for p in re.split(r"\n{2,}", html) if p.strip()]
    return "".join("<p>" + p.replace("\n", "<br>") + "</p>" for p in paragraphs)


def descriptions_to_html(apps, schema_editor):
    """Convert existing plain-text competition descriptions to safe HTML.

    Descriptions used to be plain text rendered with |linebreaks; they are now stored and
    rendered as sanitized HTML, so convert the existing values once. No-op on a fresh/CI
    database (no rows).
    """
    Competition = apps.get_model("calendar_app", "Competition")
    for comp in Competition.objects.all().iterator():
        changed = []
        for field in _FIELDS:
            value = getattr(comp, field, "") or ""
            if value:
                setattr(comp, field, _plain_to_html(value))
                changed.append(field)
        if changed:
            comp.save(update_fields=changed)


class Migration(migrations.Migration):
    dependencies = [
        ("calendar_app", "0012_competition_relay_fields"),
    ]

    operations = [
        migrations.RunPython(descriptions_to_html, migrations.RunPython.noop),
    ]
