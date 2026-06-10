from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("registrations", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="competitionregistration",
            name="participant_names",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AlterField(
            model_name="competitionregistration",
            name="first_name",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AlterField(
            model_name="competitionregistration",
            name="last_name",
            field=models.CharField(blank=True, max_length=100),
        ),
    ]
