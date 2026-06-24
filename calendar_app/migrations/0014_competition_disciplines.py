from django.db import migrations, models


def copy_discipline_to_disciplines(apps, schema_editor):
    """Carry each competition's single discipline into the new many-to-many set."""
    Competition = apps.get_model("calendar_app", "Competition")
    for comp in Competition.objects.exclude(discipline__isnull=True).iterator():
        comp.disciplines.add(comp.discipline_id)


def copy_disciplines_to_discipline(apps, schema_editor):
    """Reverse: collapse the many-to-many set back to the first discipline (best effort)."""
    Competition = apps.get_model("calendar_app", "Competition")
    for comp in Competition.objects.iterator():
        first = comp.disciplines.first()
        if first is not None:
            comp.discipline_id = first.pk
            comp.save(update_fields=["discipline"])


class Migration(migrations.Migration):
    dependencies = [
        ("calendar_app", "0013_descriptions_to_html"),
    ]

    operations = [
        migrations.AddField(
            model_name="competition",
            name="disciplines",
            field=models.ManyToManyField(blank=True, related_name="competitions", to="calendar_app.discipline"),
        ),
        migrations.RunPython(copy_discipline_to_disciplines, copy_disciplines_to_discipline),
        migrations.RemoveField(
            model_name="competition",
            name="discipline",
        ),
    ]
