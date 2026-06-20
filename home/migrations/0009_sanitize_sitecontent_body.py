from django.db import migrations

from cycling_site.sanitize import sanitize_rich_html

_BODY_FIELDS = ("body", "body_ru", "body_kk", "body_en")


def sanitize_existing_body(apps, schema_editor):
    """Backfill: run the existing SiteContent body columns through the same sanitizer that
    SiteContent.save() now applies. The home page renders these via |safe, so any HTML stored
    before sanitization was added could otherwise remain an active stored XSS until the next
    manual edit. Idempotent (sanitize_rich_html is); a no-op on a fresh database.
    """
    SiteContent = apps.get_model("home", "SiteContent")
    for obj in SiteContent.objects.all():
        changed = []
        for field in _BODY_FIELDS:
            value = getattr(obj, field, None)
            if value:
                cleaned = sanitize_rich_html(value, allow_img=True)
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
