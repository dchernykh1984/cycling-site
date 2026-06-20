from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("knowledge", "0009_delete_knowledge_pages_data"),
        ("locations", "0011_remove_location_knowledge_article"),
    ]

    # Delete bottom-up so no table is dropped while another still has a FK to it:
    # LocationArticlePage (MTI child of KnowledgeArticlePage) and KnowledgeArticlePageTag
    # both reference KnowledgeArticlePage, so they go first.
    operations = [
        migrations.DeleteModel(name="LocationArticlePage"),
        migrations.DeleteModel(name="KnowledgeArticlePageTag"),
        migrations.DeleteModel(name="KnowledgeArticlePage"),
    ]
