"""Which calendar pages a search engine should index (calendar_app.listing_seo.index_policy).

Every filter and date combination used to name itself canonical, so an engine was offered an endless
supply of near-duplicates ("Google chose a different canonical") and empty lists ("soft 404").
"""

import datetime
import html
import re

from django.test import TestCase
from django.utils import timezone

from calendar_app.models import Competition
from locations.models import Location


def _canonical(response):
    return html.unescape(re.search(r'<link rel="canonical" href="([^"]*)"', response.content.decode()).group(1))


def _alternates(response):
    found = re.findall(r'<link rel="alternate" hreflang="[^"]*" href="([^"]*)"', response.content.decode())
    return [html.unescape(url) for url in found]


class ListingIndexTests(TestCase):
    def setUp(self):
        country = Location.add_root(name_ru="Country", name_en="Country")
        self.city = country.add_child(name_ru="City", name_en="City")
        self.empty_city = country.add_child(name_ru="Quiet", name_en="Quiet")
        Competition.objects.create(
            title_ru="Race",
            date_start=timezone.localdate() + datetime.timedelta(days=5),
            status=Competition.Status.APPROVED,
            location=self.city,
        )

    def test_the_plain_pages_are_indexed_as_themselves(self):
        for path in ("/ru/calendar/", "/ru/calendar/list/", "/ru/calendar/map/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertNotIn("X-Robots-Tag", response)
                self.assertEqual(_canonical(response), f"http://testserver{path}")

    def test_a_list_about_one_place_is_a_page_of_its_own(self):
        response = self.client.get(f"/ru/calendar/list/?location={self.city.pk}")
        self.assertNotIn("X-Robots-Tag", response)
        self.assertEqual(_canonical(response), f"http://testserver/ru/calendar/list/?location={self.city.pk}")

    def test_the_dates_a_place_was_opened_on_are_not_another_page(self):
        today = timezone.localdate()
        month_ahead = today + datetime.timedelta(days=30)
        query = f"location={self.city.pk}&date_from={today}&date_to={month_ahead}"
        response = self.client.get(f"/ru/calendar/list/?{query}")
        self.assertNotIn("X-Robots-Tag", response)
        self.assertEqual(_canonical(response), f"http://testserver/ru/calendar/list/?location={self.city.pk}")
        self.assertIn(f"http://testserver/kk/calendar/list/?location={self.city.pk}", _alternates(response))

    def test_a_later_page_of_a_place_is_itself(self):
        Competition.objects.bulk_create(
            Competition(
                title_ru=f"Race {n}",
                date_start=timezone.localdate() + datetime.timedelta(days=6 + n),
                status=Competition.Status.APPROVED,
                location=self.city,
            )
            for n in range(25)
        )
        response = self.client.get(f"/ru/calendar/list/?location={self.city.pk}&page=2")
        self.assertNotIn("X-Robots-Tag", response)
        self.assertEqual(_canonical(response), f"http://testserver/ru/calendar/list/?location={self.city.pk}&page=2")

    def test_an_empty_list_stays_out_of_the_index(self):
        response = self.client.get(f"/ru/calendar/list/?location={self.empty_city.pk}")
        self.assertEqual(response["X-Robots-Tag"], "noindex")

    def test_views_of_a_page_stay_out_of_the_index(self):
        for path in (
            f"/ru/calendar/list/?location={self.city.pk}&discipline=1",
            f"/ru/calendar/list/?location={self.city.pk},{self.empty_city.pk}",
            "/ru/calendar/list/?date_from=2026-09-25&date_to=2026-10-26",
            "/ru/calendar/list/?reset=1",
            f"/ru/calendar/?location={self.city.pk}&date_from=2026-09-18",
            f"/ru/calendar/map/?location={self.city.pk}&date_from=2026-10-15",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path)["X-Robots-Tag"], "noindex")

    def test_a_cleared_filter_is_no_filter(self):
        # "?location=" is what a cleared select submits: the plain page, not a view of it.
        response = self.client.get("/ru/calendar/list/?location=")
        self.assertNotIn("X-Robots-Tag", response)
