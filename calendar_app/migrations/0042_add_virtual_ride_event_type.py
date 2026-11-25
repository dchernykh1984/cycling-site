"""A virtual ride, its own type of event: a ride or a race ridden together on the site's virtual ride page.

The virtual ride's "Add event" fills the event form with it (issue: the maintainer's, 2026-11-25); before, a ride
ridden online had no type that said so. Naming it is all this does: no existing event is moved onto it.
"""

from django.db import migrations

NAMES = {
    "name": "Виртуальный заезд",
    "name_ru": "Виртуальный заезд",
    "name_kk": "Виртуалды заезд",
    "name_en": "Virtual Ride",
}


def add_virtual_ride(apps, schema_editor):
    EventType = apps.get_model("calendar_app", "EventType")
    # Keyed on the English name, as 0028 is: replaying this on a restored backup adds no second copy
    if EventType.objects.filter(name_en=NAMES["name_en"]).exists():
        return
    last = EventType.objects.order_by("-order").values_list("order", flat=True).first() or 0
    EventType.objects.create(order=last + 1, **NAMES)


def remove_virtual_ride(apps, schema_editor):
    """Remove it again -- unless an event is marked with it, which would lose that mark."""
    EventType = apps.get_model("calendar_app", "EventType")
    event_type = EventType.objects.filter(name_en=NAMES["name_en"]).first()
    if event_type is None:
        return
    if event_type.competitions.exists():
        raise RuntimeError("Cannot reverse 0042: events are marked as a virtual ride, and removing it would drop that.")
    event_type.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("calendar_app", "0041_add_combined_events_category"),
    ]

    operations = [
        migrations.RunPython(add_virtual_ride, remove_virtual_ride),
    ]
