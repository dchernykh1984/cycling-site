from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("calendar_app", "0002_competition_upload_token"),
    ]

    operations = [
        migrations.AddField(
            model_name="competition",
            name="registration_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="competition",
            name="registration_mode",
            field=models.CharField(
                blank=True,
                choices=[
                    ("self_only", "Self only (linked to user account)"),
                    ("free", "Free (can register any person)"),
                ],
                default="self_only",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="competition",
            name="birth_date_mode",
            field=models.CharField(
                blank=True,
                choices=[("year", "Year of birth"), ("date", "Full birth date")],
                default="year",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="competition",
            name="require_approval",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="competition",
            name="require_payment",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="competition",
            name="allow_multiple_registrations",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="competition",
            name="registration_deadline",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="competition",
            name="max_participants",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="competition",
            name="show_unapproved_in_list",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="competition",
            name="show_unpaid_in_list",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="competition",
            name="show_approval_status_col",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="competition",
            name="show_payment_status_col",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="competition",
            name="show_additional_info_field",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="competition",
            name="registration_mode_locked",
            field=models.BooleanField(default=False),
        ),
    ]
