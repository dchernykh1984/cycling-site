import os

from django.db import migrations


def create_initial_superuser(apps, schema_editor):
    username = os.environ.get("INITIAL_SUPERUSER_USERNAME")
    password = os.environ.get("INITIAL_SUPERUSER_PASSWORD")

    if not username or not password:
        return  # env vars not set -- skip silently

    from accounts.models import User  # use real model, not historical state

    if User.objects.filter(username=username).exists():
        return  # already exists -- idempotent

    email = os.environ.get("INITIAL_SUPERUSER_EMAIL", f"{username}@localhost")
    User.objects.create_superuser(username=username, email=email, password=password)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_initial_superuser, migrations.RunPython.noop),
    ]
