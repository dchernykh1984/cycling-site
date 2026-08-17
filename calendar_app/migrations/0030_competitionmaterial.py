"""Hold the named links to an event's photo and video coverage.

An empty table on every existing competition: the section only appears once someone adds a link, so
nothing on the calendar changes until an organizer fills one in.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("calendar_app", "0029_competition_event_types"),
    ]

    operations = [
        migrations.CreateModel(
            name="CompetitionMaterial",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("url", models.URLField()),
                ("order", models.PositiveIntegerField(default=0)),
                (
                    "competition",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="materials",
                        to="calendar_app.competition",
                    ),
                ),
            ],
            options={
                "verbose_name": "Competition material",
                "ordering": ["order", "pk"],
            },
        ),
    ]
