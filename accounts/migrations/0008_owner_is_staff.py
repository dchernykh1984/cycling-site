from django.db import migrations


def set_owner_is_staff(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(role="owner").update(is_staff=True)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0007_rename_role_groups"),
    ]

    operations = [
        migrations.RunPython(set_owner_is_staff, migrations.RunPython.noop),
    ]
