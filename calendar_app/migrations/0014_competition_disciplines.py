from django.db import migrations, models
from django.db.models import Count


def copy_discipline_to_disciplines(apps, schema_editor):
    """Carry each competition's single discipline into the new many-to-many set."""
    Competition = apps.get_model("calendar_app", "Competition")
    for comp in Competition.objects.exclude(discipline__isnull=True).iterator():
        comp.disciplines.add(comp.discipline_id)


def copy_disciplines_to_discipline(apps, schema_editor):
    """Reverse: restore the single discipline FK. Refuse the rollback if any competition has
    several disciplines, since collapsing them to one column would silently drop data."""
    Competition = apps.get_model("calendar_app", "Competition")
    multi = list(Competition.objects.annotate(n=Count("disciplines")).filter(n__gt=1).values_list("pk", flat=True))
    if multi:
        raise RuntimeError(
            f"Cannot reverse 0014: competitions {multi} have multiple disciplines; "
            "collapsing them to a single discipline would lose data."
        )
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
