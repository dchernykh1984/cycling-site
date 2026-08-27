"""Announcing a published page to the engines that still accept being told.

The two things that must hold: a page that is public gets announced, and nothing announces while
the site has no key -- which is the state in every test and every developer's checkout, and the
only thing standing between a test run and a live HTTP call to Bing.
"""

import datetime
from unittest import mock

from django.test import TestCase, override_settings

from calendar_app.models import Competition
from cycling_site import indexnow
from locations.models import add_location_child
from news.models import NewsArticle

KEY = "0123456789abcdef0123456789abcdef"


class SubmitTests(TestCase):
    @override_settings(INDEXNOW_KEY="", SITE_BASE_URL="https://example.test")
    def test_without_a_key_nothing_is_sent(self):
        with mock.patch("cycling_site.indexnow.requests.post") as post:
            indexnow.submit(["/calendar/1/"])
        post.assert_not_called()

    @override_settings(INDEXNOW_KEY=KEY, SITE_BASE_URL="")
    def test_without_a_base_url_nothing_is_sent(self):
        """No host means no way to build an absolute URL, and IndexNow takes nothing else."""
        with mock.patch("cycling_site.indexnow.requests.post") as post:
            indexnow.submit(["/calendar/1/"])
        post.assert_not_called()

    @override_settings(INDEXNOW_KEY=KEY, SITE_BASE_URL="https://example.test")
    def test_a_submission_carries_absolute_urls_the_key_and_the_host(self):
        with mock.patch("cycling_site.indexnow.requests.post") as post:
            post.return_value = mock.Mock(status_code=200, text="")
            indexnow._post(["https://example.test/calendar/1/"], KEY, "example.test")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["host"], "example.test")
        self.assertEqual(payload["key"], KEY)
        self.assertEqual(payload["keyLocation"], f"https://example.test/{KEY}.txt")
        self.assertEqual(payload["urlList"], ["https://example.test/calendar/1/"])

    @override_settings(INDEXNOW_KEY=KEY, SITE_BASE_URL="https://example.test")
    def test_a_refusal_is_logged_and_not_raised(self):
        """A search engine being unreachable must never turn someone's approval into an error."""
        with mock.patch("cycling_site.indexnow.requests.post") as post:
            post.return_value = mock.Mock(status_code=403, text="quota")
            with self.assertLogs("cycling_site.indexnow", level="WARNING"):
                indexnow._post(["https://example.test/calendar/1/"], KEY, "example.test")


@override_settings(INDEXNOW_KEY=KEY, SITE_BASE_URL="https://example.test")
class PublishTriggersTests(TestCase):
    """Wired to the model, so it fires whichever door the page came through."""

    @classmethod
    def setUpTestData(cls):
        country = add_location_child(None, name="Kazakhstan", name_ru="Kazakhstan")
        region = add_location_child(country, name="Almaty region", name_ru="Almaty region")
        city = add_location_child(region, name="Almaty", name_ru="Almaty")
        cls.venue = add_location_child(city, name="Republic Square", name_ru="Republic Square")

    def _announced(self, action):
        with mock.patch("cycling_site.indexnow.submit") as submit:
            action()
        return [call.args[0] for call in submit.call_args_list]

    def test_approving_an_event_announces_its_page(self):
        competition = Competition.objects.create(
            title_ru="Autumn race",
            date_start=datetime.date.today() + datetime.timedelta(days=7),
            status=Competition.Status.PENDING_APPROVAL,
            location=self.venue,
        )
        announced = self._announced(lambda: competition.approve(reviewer=None))
        self.assertIn(competition.get_absolute_url(), [path for paths in announced for path in paths])

    def test_every_language_of_a_page_is_announced(self):
        """Each language is its own indexable address; announcing one leaves the others unseen."""
        competition = Competition.objects.create(
            title_ru="Winter race",
            date_start=datetime.date.today() + datetime.timedelta(days=9),
            status=Competition.Status.PENDING_APPROVAL,
            location=self.venue,
        )
        announced = self._announced(lambda: competition.approve(reviewer=None))
        paths = next(group for group in announced if any("/calendar/" in one for one in group))
        self.assertEqual(
            sorted(paths),
            sorted(f"/{code}/calendar/{competition.pk}/" for code in ("ru", "kk", "en")),
        )

    def test_an_event_still_awaiting_approval_is_not_announced(self):
        def submit_one():
            Competition.objects.create(
                title_ru="Unapproved race",
                date_start=datetime.date.today() + datetime.timedelta(days=7),
                status=Competition.Status.PENDING_APPROVAL,
                location=self.venue,
            )

        self.assertEqual(self._announced(submit_one), [])

    def test_a_hidden_event_is_not_announced(self):
        def hide():
            Competition.objects.create(
                title_ru="Hidden race",
                date_start=datetime.date.today() + datetime.timedelta(days=7),
                status=Competition.Status.APPROVED,
                is_hidden=True,
                location=self.venue,
            )

        self.assertEqual(self._announced(hide), [])

    def test_publishing_news_announces_the_article(self):
        holder = {}

        def publish():
            holder["article"] = NewsArticle.objects.create(title_ru="Team news")

        announced = self._announced(publish)
        self.assertIn(holder["article"].get_absolute_url(), [path for paths in announced for path in paths])


class KeyFileTests(TestCase):
    @override_settings(INDEXNOW_KEY=KEY)
    def test_the_key_file_serves_the_key(self):
        response = self.client.get(f"/{KEY}.txt")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode().strip(), KEY)

    @override_settings(INDEXNOW_KEY=KEY)
    def test_any_other_name_is_not_found(self):
        self.assertEqual(self.client.get("/deadbeefdeadbeef.txt").status_code, 404)

    @override_settings(INDEXNOW_KEY="")
    def test_with_no_key_configured_there_is_no_file(self):
        self.assertEqual(self.client.get(f"/{KEY}.txt").status_code, 404)
