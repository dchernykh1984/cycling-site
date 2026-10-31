from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from knowledge.models import KnowledgeArticle
from locations.models import Location, LocationProposal
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


class PlacesInSearchTests(TestCase):
    """A place awaiting review is its proposer's and its moderators' until it is approved (FR-LOC-003)."""

    def setUp(self):
        self.proposer = User.objects.create_user("proposer", "p@example.com", "pw", role=User.Role.PARTICIPANT)
        region = Location.add_root(name_ru="Testland", name_en="Testland").add_child(name_ru="Region", name_en="Region")
        city = region.add_child(name_ru="Testville", name_en="Testville")
        city.add_child(name_ru="Zzpublicvenue", name_en="Zzpublicvenue")
        pending = city.add_child(name_ru="Zzpendingvenue", name_en="Zzpendingvenue")
        LocationProposal.objects.create(location=pending, submitted_by=self.proposer)

    def _found(self, name: str, user=None) -> bool:
        browser = Client()
        if user is not None:
            browser.force_login(user)
        page = browser.get("/en/search/", {"query": name})
        return name in [place.name_en for place in page.context["location_results"]]

    def test_a_place_awaiting_review_is_found_by_its_proposer_and_the_moderators_alone(self):
        other = User.objects.create_user("other", "o@example.com", "pw", role=User.Role.PARTICIPANT)
        admin = User.objects.create_user("admin", "a@example.com", "pw", role=User.Role.ADMIN)
        for who, user, expected in (
            ("visitor", None, False),
            ("another member", other, False),
            ("proposer", self.proposer, True),
            ("admin", admin, True),
        ):
            with self.subTest(who=who):
                self.assertEqual(self._found("Zzpendingvenue", user), expected)

    def test_an_approved_place_is_found_by_anybody(self):
        self.assertTrue(self._found("Zzpublicvenue"))

    def test_finding_more_places_asks_the_database_no_more_often(self):
        city = Location.objects.get(name_en="Testville")
        Client().get("/en/search/", {"query": "Zzmanyvenue"})  # the first page of a test also fills caches
        counts = []
        for _ in range(2):
            for _ in range(3):
                venue = city.add_child(name_ru="Zzmanyvenue", name_en="Zzmanyvenue")
                LocationProposal.objects.create(location=venue, submitted_by=self.proposer)
            with CaptureQueriesContext(connection) as captured:
                Client().get("/en/search/", {"query": "Zzmanyvenue"})
            counts.append(len(captured.captured_queries))
        self.assertEqual(counts[0], counts[1])
