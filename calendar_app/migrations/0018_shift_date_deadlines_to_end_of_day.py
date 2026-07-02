"""Preserve the old "open all day of the deadline" semantics after DateField -> DateTimeField.

0017 changed registration_deadline to a DateTimeField, storing each legacy date as midnight.
is_registration_open() now compares against the exact moment, which would close registration at
the start of the deadline day instead of the end. Shift those legacy midnight values to
23:59:59 of the same calendar day in the business timezone.
"""

import datetime

from django.db import migrations


def _forward(apps, schema_editor):
    from calendar_app.registration_deadline import date_only_to_end_of_day

    Competition = apps.get_model("calendar_app", "Competition")
    for comp in Competition.objects.filter(registration_deadline__isnull=False).iterator():
        d_utc = comp.registration_deadline.astimezone(datetime.UTC)
        # Only the legacy date-only values 0017 produced (exactly midnight UTC).
        if (d_utc.hour, d_utc.minute, d_utc.second, d_utc.microsecond) == (0, 0, 0, 0):
            comp.registration_deadline = date_only_to_end_of_day(comp.registration_deadline)
            comp.save(update_fields=["registration_deadline"])


class Migration(migrations.Migration):
    dependencies = [
        ("calendar_app", "0017_alter_competition_registration_deadline"),
    ]

    operations = [
        migrations.RunPython(_forward, migrations.RunPython.noop),
    ]
