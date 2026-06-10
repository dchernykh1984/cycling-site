from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("calendar_app", "0011_competition_default_location"),
    ]

    operations = [
        migrations.AddField(
            model_name="competition",
            name="relay_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="competition",
            name="relay_max_members",
            field=models.PositiveIntegerField(default=10),
        ),
    ]
