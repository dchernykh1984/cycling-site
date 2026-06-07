import django.db.models.deletion
import django.db.models.functions.text
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("calendar_app", "0003_competition_registration_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Team",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("is_deleted", models.BooleanField(db_index=True, default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Team",
                "verbose_name_plural": "Teams",
            },
        ),
        migrations.AddConstraint(
            model_name="team",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("name"),
                name="team_name_unique_ci",
            ),
        ),
        migrations.CreateModel(
            name="RegistrationCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "competition",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="registration_categories",
                        to="calendar_app.competition",
                    ),
                ),
                ("name", models.CharField(max_length=100)),
                ("male", models.BooleanField(default=True)),
                ("female", models.BooleanField(default=True)),
                ("birth_from", models.DateField(blank=True, null=True)),
                ("birth_to", models.DateField(blank=True, null=True)),
                ("laps", models.PositiveIntegerField(blank=True, null=True)),
                ("bib_from", models.PositiveIntegerField(blank=True, null=True)),
                ("bib_to", models.PositiveIntegerField(blank=True, null=True)),
                ("max_participants", models.PositiveIntegerField(blank=True, null=True)),
                ("is_deleted", models.BooleanField(db_index=True, default=False)),
                ("order", models.PositiveSmallIntegerField(default=0)),
            ],
            options={
                "ordering": ["order", "pk"],
            },
        ),
        migrations.CreateModel(
            name="CompetitionRegistration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "competition",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="registrations",
                        to="calendar_app.competition",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="competition_registrations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "registered_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("first_name", models.CharField(max_length=100)),
                ("last_name", models.CharField(max_length=100)),
                ("birth_date", models.DateField()),
                ("gender", models.CharField(choices=[("M", "Male"), ("F", "Female")], max_length=1)),
                (
                    "category",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="registrations",
                        to="registrations.registrationcategory",
                    ),
                ),
                ("city", models.CharField(blank=True, max_length=100)),
                (
                    "team",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="registrations",
                        to="registrations.team",
                    ),
                ),
                ("additional_info", models.CharField(blank=True, max_length=100)),
                ("is_approved", models.BooleanField(default=False)),
                ("is_paid", models.BooleanField(default=False)),
                ("is_rejected", models.BooleanField(default=False)),
                ("rejection_note", models.CharField(blank=True, max_length=500)),
                ("registered_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["registered_at"],
            },
        ),
    ]
