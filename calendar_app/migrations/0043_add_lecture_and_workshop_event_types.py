"""Two types of event where people gather to listen and watch rather than to move: a lecture or seminar, where someone
tells, and a workshop (a master class), where someone shows.

The maintainer's, 2026-11-25: the calendar had no word for an event that is no ride, race or outing. Naming them is all
this does: no existing event is moved onto them.
"""

from django.db import migrations

TYPES = (
    {
        "name": "Лекция / Семинар",
        "name_ru": "Лекция / Семинар",
        "name_kk": "Дәріс / Семинар",
        "name_en": "Lecture / Seminar",
    },
    {
        "name": "Мастер-класс",
        "name_ru": "Мастер-класс",
        "name_kk": "Шеберлік сыныбы",
        "name_en": "Workshop",
    },
)


def add_talks(apps, schema_editor):
    EventType = apps.get_model("calendar_app", "EventType")
    for names in TYPES:
        # Keyed on the English name, as 0028 is: replaying this on a restored backup adds no second copy
        if EventType.objects.filter(name_en=names["name_en"]).exists():
            continue
        last = EventType.objects.order_by("-order").values_list("order", flat=True).first() or 0
        EventType.objects.create(order=last + 1, **names)


def remove_talks(apps, schema_editor):
    """Remove them again -- unless an event is marked with one, which would lose that mark."""
    EventType = apps.get_model("calendar_app", "EventType")
    for names in TYPES:
        event_type = EventType.objects.filter(name_en=names["name_en"]).first()
        if event_type is None:
            continue
        if event_type.competitions.exists():
            raise RuntimeError(
                f"Cannot reverse 0043: events are marked {names['name_en']}, and removing it would drop that."
            )
        event_type.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("calendar_app", "0042_add_virtual_ride_event_type"),
    ]

    operations = [
        migrations.RunPython(add_talks, remove_talks),
    ]
