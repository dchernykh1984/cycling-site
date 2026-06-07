import uuid

from django.db import migrations, models


def _populate_upload_tokens(apps, schema_editor):
    Competition = apps.get_model("calendar_app", "Competition")
    for competition in Competition.objects.filter(upload_token__isnull=True):
        competition.upload_token = uuid.uuid4()
        competition.save(update_fields=["upload_token"])


class Migration(migrations.Migration):
    dependencies = [
        ("calendar_app", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="competition",
            name="upload_token",
            field=models.UUIDField(null=True, default=None),
        ),
        migrations.RunPython(_populate_upload_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="competition",
            name="upload_token",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
