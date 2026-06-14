from wagtail.models import Page, Site
from wagtail.test.utils import WagtailPageTestCase

from home.models import HomePage
from knowledge.models import KnowledgeArticlePage, KnowledgeIndexPage, LocationArticlePage


class SearchViewTests(WagtailPageTestCase):
    """
    Tests for the search view: query handling and pagination edge cases.
    """

    def setUp(self):
        """
        Create a default site with a homepage so search has content to find.
        """
        root_page = Page.get_first_root_node()
        Site.objects.create(hostname="testsite", root_page=root_page, is_default_site=True)
        self.homepage = HomePage(title="Home")
        root_page.add_child(instance=self.homepage)

    def _make_article(self, title="Article", is_hidden=False, is_deleted=False):
        index = KnowledgeIndexPage(title="KB Index", slug="kb-index")
        self.homepage.add_child(instance=index)
        article = KnowledgeArticlePage(
            title=title, slug=title.lower().replace(" ", "-"), is_hidden=is_hidden, is_deleted=is_deleted
        )
        index.add_child(instance=article)
        return article

    def _make_location_article(self, title="Location", is_hidden=False, is_deleted=False):
        index = KnowledgeIndexPage(title="Loc Index", slug=f"loc-index-{title.lower().replace(' ', '-')}")
        self.homepage.add_child(instance=index)
        article = LocationArticlePage(
            title=title, slug=title.lower().replace(" ", "-"), is_hidden=is_hidden, is_deleted=is_deleted
        )
        index.add_child(instance=article)
        return article

    def test_search_without_query(self):
        response = self.client.get("/search/")
        self.assertEqual(response.status_code, 200)

    def test_search_with_query(self):
        response = self.client.get("/search/", {"query": "Home"})
        self.assertEqual(response.status_code, 200)

    def test_search_with_non_integer_page(self):
        response = self.client.get("/search/", {"query": "Home", "page": "not-a-number"})
        self.assertEqual(response.status_code, 200)

    def test_search_with_out_of_range_page(self):
        response = self.client.get("/search/", {"query": "Home", "page": 9999})
        self.assertEqual(response.status_code, 200)

    def test_hidden_article_excluded_from_search(self):
        self._make_article(title="HiddenSecret", is_hidden=True)
        response = self.client.get("/search/", {"query": "HiddenSecret"})
        self.assertEqual(response.status_code, 200)
        page_ids = [r.id for r in response.context["search_results"].object_list]
        hidden_ids = list(
            KnowledgeArticlePage.objects.filter(title="HiddenSecret").values_list("page_ptr_id", flat=True)
        )
        for hid in hidden_ids:
            self.assertNotIn(hid, page_ids)

    def test_deleted_article_excluded_from_search(self):
        self._make_article(title="DeletedSecret", is_deleted=True)
        response = self.client.get("/search/", {"query": "DeletedSecret"})
        self.assertEqual(response.status_code, 200)
        page_ids = [r.id for r in response.context["search_results"].object_list]
        deleted_ids = list(
            KnowledgeArticlePage.objects.filter(title="DeletedSecret").values_list("page_ptr_id", flat=True)
        )
        for did in deleted_ids:
            self.assertNotIn(did, page_ids)

    def test_hidden_location_article_excluded_from_search(self):
        self._make_location_article(title="HiddenRoute", is_hidden=True)
        response = self.client.get("/search/", {"query": "HiddenRoute"})
        self.assertEqual(response.status_code, 200)
        page_ids = [r.id for r in response.context["search_results"].object_list]
        hidden_ids = list(LocationArticlePage.objects.filter(title="HiddenRoute").values_list("page_ptr_id", flat=True))
        for hid in hidden_ids:
            self.assertNotIn(hid, page_ids)

    def test_deleted_location_article_excluded_from_search(self):
        self._make_location_article(title="DeletedRoute", is_deleted=True)
        response = self.client.get("/search/", {"query": "DeletedRoute"})
        self.assertEqual(response.status_code, 200)
        page_ids = [r.id for r in response.context["search_results"].object_list]
        deleted_ids = list(
            LocationArticlePage.objects.filter(title="DeletedRoute").values_list("page_ptr_id", flat=True)
        )
        for did in deleted_ids:
            self.assertNotIn(did, page_ids)
