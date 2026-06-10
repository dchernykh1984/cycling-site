import unittest.mock
import uuid

from django.db import migrations


def create_news_index_pages(apps, schema_editor):
    from wagtail.models import Locale, Page

    from home.models import HomePage
    from news.models import NewsIndexPage

    translation_key = uuid.uuid4()

    for lang_code in ("ru", "kk", "en"):
        locale = Locale.objects.filter(language_code=lang_code).first()
        if not locale:
            continue
        if NewsIndexPage.objects.filter(locale=locale).exists():
            continue
        home = HomePage.objects.filter(locale=locale, depth=2).first()
        if not home:
            continue
        page = NewsIndexPage(
            title="Новости" if lang_code == "ru" else "News",
            draft_title="Новости" if lang_code == "ru" else "News",
            slug="news",
            locale=locale,
            translation_key=translation_key,
            live=True,
        )
        with unittest.mock.patch.object(Page, "_check_slug_is_unique"):
            home.add_child(instance=page)


def remove_news_index_pages(apps, schema_editor):
    from news.models import NewsIndexPage

    NewsIndexPage.objects.filter(slug="news").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("news", "0003_add_is_hidden_is_deleted"),
        ("home", "0007_locale_homepages"),
    ]

    operations = [
        migrations.RunPython(create_news_index_pages, remove_news_index_pages),
    ]
