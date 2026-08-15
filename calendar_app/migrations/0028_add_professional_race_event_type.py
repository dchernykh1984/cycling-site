"""Give an elite start a type of its own, beside "Race" and "Kids Race".

Until now every competition on the calendar was an amateur one -- the events agent is told to skip
federation races outright -- so the list of types had no word for a start that is closed to anyone
without a licence. A reader sorting the calendar could not tell the two apart, and an organizer
posting one had nothing to mark it with.

Naming it is all this does. Nothing on the site treats the new type differently, and no existing
event is moved onto it: the ones already there really are the amateur starts they say they are.
"""

from django.db import migrations

NAMES = {
    "name": "Профессиональная гонка",
    "name_ru": "Профессиональная гонка",
    "name_kk": "Кәсіби жарыс",
    "name_en": "Professional Race",
}


def add_professional_race(apps, schema_editor):
    EventType = apps.get_model("calendar_app", "EventType")
    # Keyed on the English name: it is the one locale every seeded type is guaranteed to carry, and
    # replaying this on a restored backup must not add a second copy.
    existing = EventType.objects.filter(name_en=NAMES["name_en"]).first()
    if existing is not None:
        return
    # The list is shown in ``order``, and the field defaults to 0 -- which would put the newest type
    # at the top of every dropdown, ahead of the plain race. It belongs after the ones already
    # there, so it is numbered past the last of them.
    last = EventType.objects.order_by("-order").values_list("order", flat=True).first() or 0
    EventType.objects.create(order=last + 1, **NAMES)


def remove_professional_race(apps, schema_editor):
    """Remove it again -- unless a competition has been marked with it, which would lose that mark."""
    EventType = apps.get_model("calendar_app", "EventType")
    Competition = apps.get_model("calendar_app", "Competition")
    event_type = EventType.objects.filter(name_en=NAMES["name_en"]).first()
    if event_type is None:
        return
    in_use = Competition.objects.filter(event_type=event_type).exists()
    if in_use:
        raise RuntimeError(
            "Cannot reverse 0028: competitions are marked as a professional race, "
            "and removing the type would silently drop that."
        )
    event_type.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("calendar_app", "0027_rename_leisure_ride_event_type"),
    ]

    operations = [
        migrations.RunPython(add_professional_race, remove_professional_race),
    ]
