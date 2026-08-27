from django.test import TestCase

from knowledge.models import KnowledgeArticle
from tests.language_urls import in_language


class SearchViewTests(TestCase):
    """Search view: query handling, pagination edge cases, and knowledge-article results."""

    def test_search_without_query(self):
        self.assertEqual(self.client.get("/ru/search/").status_code, 200)

    def test_search_with_query(self):
        self.assertEqual(self.client.get("/ru/search/", {"query": "Home"}).status_code, 200)

    def test_search_with_non_integer_page(self):
        self.assertEqual(self.client.get("/ru/search/", {"query": "Home", "page": "not-a-number"}).status_code, 200)

    def test_search_with_out_of_range_page(self):
        self.assertEqual(self.client.get("/ru/search/", {"query": "Home", "page": 9999}).status_code, 200)

    def test_visible_article_found(self):
        from wagtail.search.backends import get_search_backend

        art = KnowledgeArticle.objects.create(title="VisibleGuide", locale="ru", body="<p>guide</p>")
        get_search_backend().add(art)
        resp = self.client.get(in_language("/ru/search/", "ru"), {"query": "VisibleGuide"}, HTTP_ACCEPT_LANGUAGE="ru")
        self.assertEqual(resp.status_code, 200)
        titles = [a.title for a in resp.context["knowledge_results"]]
        self.assertIn("VisibleGuide", titles)

    def test_hidden_article_excluded_from_search(self):
        from wagtail.search.backends import get_search_backend

        art = KnowledgeArticle.objects.create(title="HiddenSecret", locale="ru", is_hidden=True)
        get_search_backend().add(art)
        resp = self.client.get(in_language("/ru/search/", "ru"), {"query": "HiddenSecret"}, HTTP_ACCEPT_LANGUAGE="ru")
        titles = [a.title for a in resp.context["knowledge_results"]]
        self.assertNotIn("HiddenSecret", titles)

    def test_deleted_article_excluded_from_search(self):
        from wagtail.search.backends import get_search_backend

        art = KnowledgeArticle.objects.create(title="DeletedSecret", locale="ru", is_deleted=True)
        get_search_backend().add(art)
        resp = self.client.get(in_language("/ru/search/", "ru"), {"query": "DeletedSecret"}, HTTP_ACCEPT_LANGUAGE="ru")
        titles = [a.title for a in resp.context["knowledge_results"]]
        self.assertNotIn("DeletedSecret", titles)
