import django.db.models.deletion
from django.db import migrations, models

FALLBACK_NAMES = {
    "Другая локация",
    "Басқа орын",
    "Other location",
}
STEPLEN = 4


def mark_existing_fallbacks(apps, schema_editor):
    Location = apps.get_model("locations", "Location")
    LocationFallback = apps.get_model("locations", "LocationFallback")
    candidates = (
        Location.objects.filter(depth=4, is_hidden=True, is_deleted=False)
        .filter(
            models.Q(name_ru__in=FALLBACK_NAMES)
            | models.Q(name_kk__in=FALLBACK_NAMES)
            | models.Q(name_en__in=FALLBACK_NAMES)
        )
        .order_by("path")
    )
    assigned_cities = set()
    for location in candidates.iterator():
        parent_path = location.path[:-STEPLEN]
        city = Location.objects.filter(path=parent_path, depth=3).first()
        if city is None or city.pk in assigned_cities:
            continue
        LocationFallback.objects.create(city_id=city.pk, location_id=location.pk)
        assigned_cities.add(city.pk)


class Migration(migrations.Migration):
    dependencies = [
        ("locations", "0011_remove_location_knowledge_article"),
    ]

    operations = [
        migrations.CreateModel(
            name="LocationFallback",
            fields=[
                (
                    "id",
                    models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
                ),
                (
                    "city",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fallback_mapping",
                        to="locations.location",
                    ),
                ),
                (
                    "location",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fallback_identity",
                        to="locations.location",
                    ),
                ),
            ],
        ),
        migrations.RunPython(mark_existing_fallbacks, migrations.RunPython.noop),
    ]
