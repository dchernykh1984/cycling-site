import json

from django.db import migrations
from django.utils import timezone


def copy_pages_to_articles(apps, schema_editor):
    """Copy existing KnowledgeArticlePage (Wagtail) rows into the plain KnowledgeArticle model.

    Bodies were stored as a StreamField; every existing article is a single (or several)
    "text" RichText block(s) of already-sanitized HTML, so we concatenate the text blocks.
    Non-text blocks (image/embed/code) don't exist in the data and are ignored. Self-contained
    (no app-code import); a no-op on a fresh database with no pages.
    """
    KnowledgeArticlePage = apps.get_model("knowledge", "KnowledgeArticlePage")
    KnowledgeArticle = apps.get_model("knowledge", "KnowledgeArticle")
    Locale = apps.get_model("wagtailcore", "Locale")
    locale_code = {loc.pk: loc.language_code for loc in Locale.objects.all()}

    for page in KnowledgeArticlePage.objects.all().iterator():
        raw = page.body
        try:
            blocks = raw.raw_data
        except AttributeError:
            blocks = json.loads(raw) if raw else []
        body_html = "".join(b.get("value", "") for b in blocks if b.get("type") == "text")
        KnowledgeArticle.objects.create(
            title=page.title,
            slug=page.slug,
            locale=locale_code.get(page.locale_id, "ru"),
            body=body_html,
            category=page.category or "",
            published_by_id=page.published_by_id,
            published_at=page.published_at or page.first_published_at or timezone.now(),
            is_hidden=page.is_hidden,
            is_deleted=page.is_deleted,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("knowledge", "0007_knowledgearticle"),
    ]

    operations = [
        migrations.RunPython(copy_pages_to_articles, migrations.RunPython.noop),
    ]
