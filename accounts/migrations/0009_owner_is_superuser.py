from django.db import migrations


def set_owner_is_superuser(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(role="owner").update(is_superuser=True)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_owner_is_staff"),
    ]

    operations = [
        migrations.RunPython(set_owner_is_superuser, migrations.RunPython.noop),
    ]
