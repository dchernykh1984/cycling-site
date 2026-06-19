import re

from django.db import migrations

# Crude "already looks like HTML" guard so the migration is idempotent and a no-op on
# descriptions that are already rich HTML (and on fresh/CI databases with no rows).
_LOOKS_LIKE_HTML = re.compile(r"<[a-zA-Z/]")
_FIELDS = ("description", "description_ru", "description_kk", "description_en")


def plaintext_to_html(apps, schema_editor):
    """Convert existing plain-text competition descriptions to safe HTML.

    Descriptions used to be plain text rendered with |linebreaks; they are now stored and
    rendered as sanitized HTML. Convert the existing values (escape, linkify URLs into
    new-tab links, keep paragraphs) so they keep displaying correctly.
    """
    from cycling_site.sanitize import plaintext_to_html as convert

    Competition = apps.get_model("calendar_app", "Competition")
    for comp in Competition.objects.all().iterator():
        changed = []
        for field in _FIELDS:
            value = getattr(comp, field, "") or ""
            if value and not _LOOKS_LIKE_HTML.search(value):
                setattr(comp, field, convert(value))
                changed.append(field)
        if changed:
            comp.save(update_fields=changed)


class Migration(migrations.Migration):
    dependencies = [
        ("calendar_app", "0012_competition_relay_fields"),
    ]

    operations = [
        migrations.RunPython(plaintext_to_html, migrations.RunPython.noop),
    ]
