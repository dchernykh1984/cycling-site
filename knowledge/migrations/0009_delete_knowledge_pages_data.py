from django.db import migrations


def delete_legacy_pages(apps, schema_editor):
    """Remove the legacy Wagtail knowledge pages from the page tree.

    Their content was copied into the plain KnowledgeArticle model in 0008. We delete via
    the real Page model so treebeard keeps the tree consistent (numchild/paths); the schema
    DeleteModel operations follow in the next migration. No-op on a database with no pages.
    """
    from wagtail.models import Page as RealPage

    KnowledgeArticlePage = apps.get_model("knowledge", "KnowledgeArticlePage")
    LocationArticlePage = apps.get_model("knowledge", "LocationArticlePage")
    HistoricalPage = apps.get_model("wagtailcore", "Page")

    page_ids = list(KnowledgeArticlePage.objects.values_list("page_ptr_id", flat=True))
    if not page_ids:
        return
    # The real KnowledgeArticlePage class is already gone from code, so page.specific can't
    # resolve it. Delete the MTI rows bottom-up via the historical models (subclass rows,
    # then the base wagtailcore_page rows), then let treebeard repair the parent index pages.
    LocationArticlePage.objects.all().delete()
    KnowledgeArticlePage.objects.all().delete()
    HistoricalPage.objects.filter(pk__in=page_ids).delete()
    RealPage.fix_tree()


class Migration(migrations.Migration):
    dependencies = [
        ("knowledge", "0008_populate_knowledgearticle"),
    ]

    # Irreversible on purpose: the deleted Wagtail pages can't be reconstructed, so a
    # rollback must stop here rather than silently leaving the tree without its articles.
    operations = [
        migrations.RunPython(delete_legacy_pages),
    ]
