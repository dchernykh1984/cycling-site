from django.test import TestCase

from audit.models import AuditLog
from news.models import NewsArticle


class NewsArticleAuditTests(TestCase):
    """NewsArticle is the live news model, so create/update/soft-delete must be audited."""

    def _entries(self, article, **filters):
        return AuditLog.objects.filter(object_type="news.NewsArticle", object_id=str(article.pk), **filters)

    def test_create_is_audited(self):
        article = NewsArticle.objects.create(title_ru="Audited", body_ru="<p>x</p>")
        self.assertTrue(self._entries(article, action=AuditLog.ACTION_CREATED).exists())

    def test_update_is_audited(self):
        article = NewsArticle.objects.create(title_ru="Audited", body_ru="<p>x</p>")
        article.title_ru = "Audited 2"
        article.save()
        self.assertTrue(self._entries(article, action=AuditLog.ACTION_UPDATED).exists())

    def test_soft_delete_is_audited(self):
        article = NewsArticle.objects.create(title_ru="Audited", body_ru="<p>x</p>")
        article.is_deleted = True
        article.save(update_fields=["is_deleted"])
        self.assertTrue(self._entries(article, action=AuditLog.ACTION_UPDATED, changes="is_deleted").exists())
