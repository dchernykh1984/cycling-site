import json

from django.db import migrations
from django.utils import timezone


def _body_from_blocks(raw) -> str:
    """Concatenate the HTML of every "text" StreamField block into frontend HTML.

    RichTextBlock stores Wagtail's *DB* representation, where internal links/embeds look like
    ``<a linktype="page" id="N">`` (no href). expand_db_html() turns those into real frontend
    HTML (resolving hrefs) so they stay clickable after the move off Wagtail rendering; plain
    HTML passes through unchanged. (The nine production articles have no such links, but this
    keeps the conversion correct for any that do.)
    """
    from wagtail.rich_text import expand_db_html

    try:
        blocks = raw.raw_data
    except AttributeError:
        blocks = json.loads(raw) if raw else []
    html = "".join(b.get("value", "") for b in blocks if b.get("type") == "text")
    return expand_db_html(html)


def _attach_tags(tagged_item_model, content_type, object_id, tag_ids) -> None:
    """Re-create taggit links for the new model via its generic TaggedItem table."""
    for tag_id in tag_ids:
        tagged_item_model.objects.create(tag_id=tag_id, content_type=content_type, object_id=object_id)


def copy_pages_to_articles(apps, schema_editor):
    """Copy existing KnowledgeArticlePage (Wagtail) rows into the plain KnowledgeArticle model.

    Bodies were stored as a StreamField; every existing article is a single (or several)
    "text" RichText block(s) of already-sanitized HTML, so we concatenate the text blocks
    (non-text blocks don't exist in the data). Tags are re-pointed from the old
    ClusterTaggable through-model to the new model's taggit TaggedItem rows before the old
    tables are dropped in 0010. Self-contained; a no-op on a fresh database with no pages.
    """
    KnowledgeArticlePage = apps.get_model("knowledge", "KnowledgeArticlePage")
    KnowledgeArticlePageTag = apps.get_model("knowledge", "KnowledgeArticlePageTag")
    KnowledgeArticle = apps.get_model("knowledge", "KnowledgeArticle")
    Locale = apps.get_model("wagtailcore", "Locale")
    TaggedItem = apps.get_model("taggit", "TaggedItem")
    ContentType = apps.get_model("contenttypes", "ContentType")

    # The KnowledgeArticle content type may not exist yet mid-migrate (created post_migrate).
    article_ct, _ = ContentType.objects.get_or_create(app_label="knowledge", model="knowledgearticle")
    locale_code = {loc.pk: loc.language_code for loc in Locale.objects.all()}

    for page in KnowledgeArticlePage.objects.all().iterator():
        article = KnowledgeArticle.objects.create(
            title=page.title,
            slug=page.slug,
            locale=locale_code.get(page.locale_id, "ru"),
            body=_body_from_blocks(page.body),
            category=page.category or "",
            published_by_id=page.published_by_id,
            published_at=page.published_at or page.first_published_at or timezone.now(),
            is_hidden=page.is_hidden,
            is_deleted=page.is_deleted,
        )
        tag_ids = list(
            KnowledgeArticlePageTag.objects.filter(content_object_id=page.pk).values_list("tag_id", flat=True)
        )
        _attach_tags(TaggedItem, article_ct, article.pk, tag_ids)


class Migration(migrations.Migration):
    dependencies = [
        ("knowledge", "0007_knowledgearticle"),
    ]

    # Irreversible on purpose: a reverse would recreate empty Wagtail tables without the
    # articles and then 0007 would drop KnowledgeArticle, silently losing data. Stop loudly.
    operations = [
        migrations.RunPython(copy_pages_to_articles),
    ]
