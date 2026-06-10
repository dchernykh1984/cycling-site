from django.db import migrations


def create_locale_homepages(apps, schema_editor):
    from wagtail.models import Locale, Page

    from home.models import HomePage

    ru_locale = Locale.objects.filter(language_code="ru").first()
    if not ru_locale:
        return

    ru_home = HomePage.objects.filter(locale=ru_locale, depth=2).first()
    if not ru_home:
        return

    root = Page.objects.get(depth=1)

    for lang_code in ("kk", "en"):
        locale = Locale.objects.filter(language_code=lang_code).first()
        if not locale:
            continue
        if HomePage.objects.filter(locale=locale, depth=2).exists():
            continue

        new_home = HomePage(
            title="Home",
            draft_title="Home",
            slug="home",
            locale=locale,
            translation_key=ru_home.translation_key,
            live=True,
        )
        root.add_child(instance=new_home)


def remove_locale_homepages(apps, schema_editor):
    from wagtail.models import Locale

    from home.models import HomePage

    for lang_code in ("kk", "en"):
        locale = Locale.objects.filter(language_code=lang_code).first()
        if locale:
            HomePage.objects.filter(locale=locale, depth=2).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("home", "0006_populate_sitecontent"),
        ("wagtailcore", "0097_baselogentry_uuid_action_timestamp_indexes"),
    ]

    operations = [
        migrations.RunPython(create_locale_homepages, remove_locale_homepages),
    ]
