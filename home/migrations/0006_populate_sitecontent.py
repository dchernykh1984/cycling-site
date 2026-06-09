"""Data migration: seed the SiteContent singleton with default values."""

from django.db import migrations


def populate(apps, schema_editor):
    SiteContent = apps.get_model("home", "SiteContent")
    SiteContent.objects.get_or_create(
        pk=1,
        defaults={
            "navbar_title": "Велоспорт",
            "navbar_title_ru": "Велоспорт",
            "navbar_title_kk": "Велоспорт",
            "navbar_title_en": "Cycling",
            "page_title": "Велоспорт",
            "page_title_ru": "Велоспорт",
            "page_title_kk": "Велоспорт",
            "page_title_en": "Home",
            "body": "",
            "body_ru": "",
            "body_kk": "",
            "body_en": "",
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("home", "0005_sitecontent"),
    ]

    operations = [
        migrations.RunPython(populate, migrations.RunPython.noop),
    ]
