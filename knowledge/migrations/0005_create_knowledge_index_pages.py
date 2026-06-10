import unittest.mock
import uuid

from django.db import migrations


def create_knowledge_index_pages(apps, schema_editor):
    from wagtail.models import Locale, Page

    from home.models import HomePage
    from knowledge.models import KnowledgeIndexPage

    translation_key = uuid.uuid4()

    for lang_code in ("ru", "kk", "en"):
        locale = Locale.objects.filter(language_code=lang_code).first()
        if not locale:
            continue
        if KnowledgeIndexPage.objects.filter(locale=locale).exists():
            continue
        home = HomePage.objects.filter(locale=locale, depth=2).first()
        if not home:
            continue
        page = KnowledgeIndexPage(
            title="База знаний" if lang_code == "ru" else "Knowledge Base",
            draft_title="База знаний" if lang_code == "ru" else "Knowledge Base",
            slug="knowledge",
            locale=locale,
            translation_key=translation_key,
            live=True,
        )
        with unittest.mock.patch.object(Page, "_check_slug_is_unique"):
            home.add_child(instance=page)


def remove_knowledge_index_pages(apps, schema_editor):
    from knowledge.models import KnowledgeIndexPage

    KnowledgeIndexPage.objects.filter(slug="knowledge").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("knowledge", "0004_add_is_hidden_to_knowledgearticlepage"),
        ("home", "0007_locale_homepages"),
    ]

    operations = [
        migrations.RunPython(create_knowledge_index_pages, remove_knowledge_index_pages),
    ]
