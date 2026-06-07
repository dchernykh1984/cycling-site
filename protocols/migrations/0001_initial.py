import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("calendar_app", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Protocol",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "protocol_type",
                    models.CharField(
                        choices=[("absolute", "Absolute"), ("group", "Group")],
                        max_length=20,
                    ),
                ),
                ("html_file", models.FileField(upload_to="protocols/")),
                ("last_updated", models.DateTimeField(auto_now=True)),
                ("is_live", models.BooleanField(default=True)),
                ("stage_label", models.CharField(blank=True, max_length=200)),
                ("file_hash", models.CharField(blank=True, max_length=64)),
                (
                    "competition",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="protocols",
                        to="calendar_app.competition",
                    ),
                ),
            ],
            options={
                "unique_together": {("competition", "protocol_type")},
            },
        ),
        migrations.CreateModel(
            name="ProtocolVersion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("html_file", models.FileField(upload_to="protocol_versions/")),
                ("saved_at", models.DateTimeField(auto_now_add=True)),
                ("file_hash", models.CharField(max_length=64)),
                (
                    "protocol",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="versions",
                        to="protocols.protocol",
                    ),
                ),
            ],
            options={
                "ordering": ["-saved_at"],
            },
        ),
    ]
