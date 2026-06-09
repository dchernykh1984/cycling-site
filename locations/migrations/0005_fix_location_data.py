"""Fix minor data issues in the initial location tree:
- Duplicate city at sort_order=5 in Abay oblast -> rename to Aksuat
- English name with mixed Cyrillic/Latin script -> Makhambyet
"""

from django.db import migrations


def fix_location_data(apps, schema_editor):
    from locations.models import Location

    # Fix duplicate Аягоз in Абайская область
    try:
        abai_oblast = Location.objects.get(name_ru="Абайская область", depth=2)
        duplicates = Location.objects.filter(
            name_ru="Аягоз",
            depth=3,
            path__startswith=abai_oblast.path,
            sort_order=5,
        )
        for dup in duplicates:
            dup.name = "Ақсуат"
            dup.name_ru = "Ақсуат"
            dup.name_kk = "Ақсуат"
            dup.name_en = "Aksuat"
            dup.save(update_fields=["name", "name_ru", "name_kk", "name_en"])
    except Location.DoesNotExist:
        pass

    # Fix mixed-script English name
    Location.objects.filter(name_en="Makhambет").update(name_en="Makhambyet")


class Migration(migrations.Migration):
    dependencies = [
        ("locations", "0004_populate_locations"),
    ]

    operations = [
        migrations.RunPython(fix_location_data, migrations.RunPython.noop),
    ]
