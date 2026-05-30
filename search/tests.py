from wagtail.models import Page, Site
from wagtail.test.utils import WagtailPageTestCase

from home.models import HomePage


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
