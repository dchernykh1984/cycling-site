from django.db import migrations


def create_locales(apps, schema_editor):
    Locale = apps.get_model("wagtailcore", "Locale")

    # On pre-Phase-2 databases, wagtailcore.0054_initial_locale was applied
    # when LANGUAGE_CODE was "en-us", so the default locale is "en-us".
    # Rename it to "ru" in-place so existing page FKs stay valid.
    # On fresh installs, 0054 already created "ru"; nothing to rename.
    for legacy_code in ("en-us", "en"):
        legacy = Locale.objects.filter(language_code=legacy_code).first()
        if legacy and not Locale.objects.filter(language_code="ru").exists():
            legacy.language_code = "ru"
            legacy.save()
            break

    # Guarantee all required locales exist regardless of starting state.
    Locale.objects.get_or_create(language_code="ru")
    Locale.objects.get_or_create(language_code="kk")
    Locale.objects.get_or_create(language_code="en")


def revert_locales(apps, schema_editor):
    Locale = apps.get_model("wagtailcore", "Locale")
    ru = Locale.objects.filter(language_code="ru").first()
    if ru:
        ru.language_code = "en-us"
        ru.save()
    Locale.objects.filter(language_code__in=["kk", "en"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("home", "0002_create_homepage"),
        ("wagtailcore", "0054_initial_locale"),
    ]

    operations = [
        migrations.RunPython(create_locales, revert_locales),
    ]
