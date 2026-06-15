import unittest.mock

from django.db import migrations


def create_locale_map_pages(apps, schema_editor):
    from wagtail.models import Locale, Page

    from home.models import HomePage
    from locations.models import LocationsMapPage

    ru_locale = Locale.objects.filter(language_code="ru").first()
    if not ru_locale:
        return
    ru_map = LocationsMapPage.objects.filter(locale=ru_locale, slug="map").first()
    if not ru_map:
        return

    for lang_code in ("kk", "en"):
        locale = Locale.objects.filter(language_code=lang_code).first()
        if not locale:
            continue
        if LocationsMapPage.objects.filter(locale=locale, slug="map").exists():
            continue
        home = HomePage.objects.filter(locale=locale, depth=2).first()
        if not home:
            continue
        page = LocationsMapPage(
            title="Map",
            draft_title="Map",
            slug="map",
            locale=locale,
            translation_key=ru_map.translation_key,
            live=True,
        )
        # Same-slug locale copies under sibling homepages: bypass global slug validation.
        with unittest.mock.patch.object(Page, "_check_slug_is_unique"):
            home.add_child(instance=page)


def remove_locale_map_pages(apps, schema_editor):
    from wagtail.models import Locale

    from locations.models import LocationsMapPage

    for lang_code in ("kk", "en"):
        locale = Locale.objects.filter(language_code=lang_code).first()
        if locale:
            LocationsMapPage.objects.filter(locale=locale, slug="map").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("locations", "0008_create_locations_map_page"),
        ("home", "0007_locale_homepages"),
    ]

    operations = [
        migrations.RunPython(create_locale_map_pages, remove_locale_map_pages),
    ]
