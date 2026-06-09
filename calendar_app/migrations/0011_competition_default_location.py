"""
For competitions that have no location set (location_id IS NULL), assign
the "Другая локация" leaf-node under
  "Другая страна" → "Другой регион" → "Другой город".

If the location tree has not been populated yet, this is a no-op.
"""

from django.db import migrations


def set_default_location(apps, schema_editor):
    from locations.models import Location

    Competition = apps.get_model("calendar_app", "Competition")

    try:
        other_country = Location.objects.get(name_ru="Другая страна", depth=1)
        other_region = Location.objects.get(name_ru="Другой регион", depth=2, path__startswith=other_country.path)
        other_city = Location.objects.get(name_ru="Другой город", depth=3, path__startswith=other_region.path)
        default_venue = Location.objects.get(name_ru="Другая локация", depth=4, path__startswith=other_city.path)
    except Location.DoesNotExist:
        return  # location data not yet populated — skip

    Competition.objects.filter(location_id__isnull=True).update(location_id=default_venue.pk)


def reverse_default_location(apps, schema_editor):
    Competition = apps.get_model("calendar_app", "Competition")
    from locations.models import Location

    try:
        other_venue = Location.objects.get(
            name_ru="Другая локация",
            depth=4,
            path__startswith=Location.objects.get(name_ru="Другая страна", depth=1).path,
        )
        Competition.objects.filter(location_id=other_venue.pk).update(location_id=None)
    except Location.DoesNotExist:
        pass


class Migration(migrations.Migration):
    dependencies = [
        ("calendar_app", "0010_populate_disciplines"),
        ("locations", "0005_fix_location_data"),
    ]

    operations = [
        migrations.RunPython(set_default_location, reverse_default_location),
    ]
