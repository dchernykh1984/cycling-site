import os

from django.db import migrations


def fix_site_hostname(apps, schema_editor):
    hostname = os.environ.get("VIRTUAL_HOST")
    if not hostname:
        return
    Site = apps.get_model("wagtailcore", "Site")
    Site.objects.filter(is_default_site=True).update(hostname=hostname, port=80)


class Migration(migrations.Migration):
    dependencies = [
        ("home", "0007_locale_homepages"),
    ]

    operations = [
        migrations.RunPython(fix_site_hostname, migrations.RunPython.noop),
    ]
