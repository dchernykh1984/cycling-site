from django.db import migrations


def create_locations_map_page(apps, schema_editor):
    from wagtail.models import Locale

    from home.models import HomePage
    from locations.models import LocationsMapPage

    ru_locale = Locale.objects.filter(language_code="ru").first()
    home = HomePage.objects.filter(locale=ru_locale, depth=2).first() if ru_locale else None
    if home is None:
        home = HomePage.objects.filter(depth=2).first()
    if home is None:
        return

    if LocationsMapPage.objects.filter(depth=3).exists():
        return

    locale = ru_locale or Locale.objects.first()
    page = LocationsMapPage(
        title="Map",
        draft_title="Map",
        slug="map",
        live=True,
        locale=locale,
    )
    home.add_child(instance=page)


def remove_locations_map_page(apps, schema_editor):
    from locations.models import LocationsMapPage

    LocationsMapPage.objects.filter(slug="map", depth=3).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("locations", "0007_add_xinjiang_border_prefectures"),
        ("home", "0008_fix_wagtail_site_hostname"),
    ]

    operations = [
        migrations.RunPython(create_locations_map_page, remove_locations_map_page),
    ]
