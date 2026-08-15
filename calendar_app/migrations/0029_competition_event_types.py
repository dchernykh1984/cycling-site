"""Let an event carry several types, the way it already carries several disciplines.

A start is often more than one thing at once -- a race with a kids race inside it, an open mass
start that also holds a professional field -- and one type per event forced those to be filed as two
separate events, or as neither. This copies each competition's single type into a set and drops the
column, exactly as 0014 did for disciplines.

The reverse refuses when any competition has come to hold more than one type, because collapsing
them back into a single column would silently drop what an organizer said about their race.
"""

from django.db import migrations, models
from django.db.models import Count


def copy_event_type_to_event_types(apps, schema_editor):
    """Carry each competition's single type into the new many-to-many set."""
    Competition = apps.get_model("calendar_app", "Competition")
    for competition in Competition.objects.exclude(event_type__isnull=True).iterator():
        competition.event_types.add(competition.event_type_id)


def copy_event_types_to_event_type(apps, schema_editor):
    Competition = apps.get_model("calendar_app", "Competition")
    several = list(Competition.objects.annotate(n=Count("event_types")).filter(n__gt=1).values_list("pk", flat=True))
    if several:
        raise RuntimeError(
            f"Cannot reverse 0029: competitions {several} have several event types; "
            "collapsing them into one column would lose data."
        )
    for competition in Competition.objects.iterator():
        first = competition.event_types.first()
        if first is not None:
            competition.event_type_id = first.pk
            competition.save(update_fields=["event_type"])


class Migration(migrations.Migration):
    dependencies = [
        ("calendar_app", "0028_add_professional_race_event_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="competition",
            name="event_types",
            field=models.ManyToManyField(blank=True, related_name="competitions", to="calendar_app.eventtype"),
        ),
        migrations.RunPython(copy_event_type_to_event_types, copy_event_types_to_event_type),
        migrations.RemoveField(
            model_name="competition",
            name="event_type",
        ),
    ]
