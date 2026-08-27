"""Filtered lists as pages people can find.

`/calendar/list/?location=2` returns the events for one city in plain HTML and always has. What it
never had was a way in: nothing linked it, and the sitemap did not know it existed, so it was a
page only someone who had already built the filter in the browser could reach.
"""

import datetime
import re

from django.test import TestCase
from django.urls import reverse

from calendar_app.listing_seo import landing_filters
from calendar_app.models import Competition, Discipline, DisciplineCategory
from locations.models import add_location_child

SOON = datetime.date.today() + datetime.timedelta(days=10)


class LandingFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        country = add_location_child(None, name="Kazakhstan", name_ru="Kazakhstan")
        region = add_location_child(country, name="Almaty region", name_ru="Almaty region")
        cls.city = add_location_child(region, name="Almaty", name_ru="Almaty")
        venue = add_location_child(cls.city, name="Republic Square", name_ru="Republic Square")
        cls.empty_city = add_location_child(region, name="Talgar", name_ru="Talgar")
        add_location_child(cls.empty_city, name="Central square", name_ru="Central square")

        category = DisciplineCategory.objects.create(name_ru="Road", name_en="Road", order=1)
        cls.discipline = Discipline.objects.create(name_ru="Criterium", name_en="Criterium", category=category, order=1)
        cls.unused = Discipline.objects.create(name_ru="Bike polo", name_en="Bike polo", category=category, order=2)
        competition = Competition.objects.create(
            title_ru="City race",
            date_start=SOON,
            status=Competition.Status.APPROVED,
            location=venue,
        )
        competition.disciplines.set([cls.discipline])

    def test_only_places_that_hold_events_are_offered(self):
        places, _kinds = landing_filters()
        self.assertIn(self.city, places)
        self.assertNotIn(self.empty_city, places)

    def test_only_disciplines_that_hold_events_are_offered(self):
        _places, kinds = landing_filters()
        self.assertIn(self.discipline, kinds)
        self.assertNotIn(self.unused, kinds)

    def test_the_calendar_links_them(self):
        html = self.client.get(reverse("calendar")).content.decode()
        without_scripts = re.sub(r"<script.*?</script>", "", html, flags=re.S)
        self.assertIn(f"?location={self.city.pk}", without_scripts)
        self.assertIn(f"?discipline={self.discipline.pk}", without_scripts)

    def test_the_sitemap_lists_them(self):
        body = self.client.get("/sitemap-calendar-filters.xml").content.decode()
        self.assertIn(f"location={self.city.pk}", body)
        self.assertIn(f"discipline={self.discipline.pk}", body)

    def test_the_index_names_the_section(self):
        self.assertIn("sitemap-calendar-filters.xml", self.client.get("/sitemap.xml").content.decode())
