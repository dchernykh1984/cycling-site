"""A filtered competition list, as a search result shows it.

The URL `/calendar/list/?location=2` has always returned the right events as plain HTML; what it
never had was any sign of what it holds. Every filter combination carried the same title and the
same site-wide description, so instead of a page per city and per discipline there was one page
repeated. "Races in Almaty" is what people type; this is what answers it.
"""

import datetime
import re

from django.test import TestCase
from django.urls import reverse

from calendar_app.models import Competition, Discipline, DisciplineCategory
from locations.models import add_location_child
from tests.language_urls import in_language

FIRST = datetime.date.today() + datetime.timedelta(days=5)
SPAN = {"date_from": FIRST.isoformat(), "date_to": (FIRST + datetime.timedelta(days=40)).isoformat()}


def _title(html):
    return re.sub(r"\s+", " ", re.search(r"<title>(.*?)</title>", html, re.S).group(1)).strip()


def _description(html):
    m = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]*)"', html)
    return m.group(1) if m else ""


class FilteredListMetaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        country = add_location_child(None, name="Kazakhstan", name_ru="Kazakhstan", name_en="Kazakhstan")
        region = add_location_child(country, name="Almaty region", name_ru="Almaty region")
        cls.city = add_location_child(region, name="Almaty", name_ru="Almaty", name_en="Almaty")
        venue = add_location_child(cls.city, name="Republic Square", name_ru="Republic Square")
        category = DisciplineCategory.objects.create(name_ru="Road", name_en="Road", order=1)
        cls.discipline = Discipline.objects.create(name_ru="Criterium", name_en="Criterium", category=category, order=1)
        comp = Competition.objects.create(
            title_ru="City race", date_start=FIRST, status=Competition.Status.APPROVED, location=venue
        )
        comp.disciplines.set([cls.discipline])

    def _get(self, **params):
        return self.client.get(
            in_language(reverse("calendar_list"), "en"), {**SPAN, **params}, HTTP_ACCEPT_LANGUAGE="en"
        ).content.decode()

    def test_a_city_filter_names_the_city_in_the_title(self):
        self.assertIn("Almaty", _title(self._get(location=self.city.pk)))

    def test_a_discipline_filter_names_the_discipline(self):
        self.assertIn("Criterium", _title(self._get(discipline=self.discipline.pk)))

    def test_the_description_says_how_many_events_there_are(self):
        description = _description(self._get(location=self.city.pk))
        self.assertIn("Almaty", description)
        self.assertRegex(description, r"\d+")

    def test_two_filters_do_not_share_a_description(self):
        by_city = _description(self._get(location=self.city.pk))
        by_discipline = _description(self._get(discipline=self.discipline.pk))
        self.assertNotEqual(by_city, by_discipline)

    def test_an_unfiltered_list_keeps_the_site_wide_text(self):
        """Nothing of its own to say, so it must not invent something."""
        self.assertNotIn("Almaty", _title(self._get()))
