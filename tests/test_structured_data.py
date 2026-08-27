"""schema.org markup on a competition page.

Without it a search engine sees prose and cannot tell the start date from a phone number, so the
event never qualifies for the rich result that shows a date and a place under the link.
"""

import datetime
import json
import re

from django.test import TestCase

from calendar_app.models import Competition, Discipline, DisciplineCategory
from locations.models import add_location_child


def _competition(title="Race", **kwargs):
    defaults = {
        "title_ru": title,
        "date_start": datetime.date.today() + datetime.timedelta(days=10),
        "status": Competition.Status.APPROVED,
    }
    defaults.update(kwargs)
    return Competition.objects.create(**defaults)


def _payload(client, comp):
    html = client.get(comp.get_absolute_url()).content.decode()
    block = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    assert block is not None, "no JSON-LD on the page"
    return json.loads(
        block.group(1)
        .replace("&quot;", '"')
        .replace("&#x27;", "'")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
    )


class SportsEventMarkupTests(TestCase):
    def test_the_page_declares_a_sports_event(self):
        comp = _competition("Marked up race")
        data = _payload(self.client, comp)
        self.assertEqual(data["@type"], "SportsEvent")
        self.assertEqual(data["name"], "Marked up race")

    def test_the_dates_are_machine_readable(self):
        comp = _competition("Two day race", date_start=datetime.date(2026, 5, 1), date_end=datetime.date(2026, 5, 3))
        data = _payload(self.client, comp)
        self.assertEqual(data["startDate"], "2026-05-01")
        self.assertEqual(data["endDate"], "2026-05-03")

    def test_a_one_day_race_has_no_end_date(self):
        comp = _competition("One day race", date_start=datetime.date(2026, 5, 1))
        self.assertNotIn("endDate", _payload(self.client, comp))

    def test_the_url_is_absolute(self):
        comp = _competition("Addressed race")
        self.assertTrue(_payload(self.client, comp)["url"].startswith("http"))

    def test_the_venue_travels_with_its_coordinates(self):
        country = add_location_child(None, name="Kazakhstan", name_ru="Kazakhstan")
        region = add_location_child(country, name="Almaty region", name_ru="Almaty region")
        city = add_location_child(region, name="Almaty", name_ru="Almaty")
        venue = add_location_child(city, name="Medeu", name_ru="Medeu", lat="43.157800", lng="77.057000")
        comp = _competition("Placed race", location=venue)
        place = _payload(self.client, comp)["location"]
        self.assertEqual(place["name"], "Medeu")
        self.assertAlmostEqual(place["geo"]["latitude"], 43.1578, places=4)
        self.assertEqual(place["address"]["addressCountry"], "Kazakhstan")

    def test_the_sport_comes_from_the_disciplines(self):
        category = DisciplineCategory.objects.create(name_ru="Road", order=1)
        discipline = Discipline.objects.create(name_ru="Criterium", category=category, order=1)
        comp = _competition("Sporting race")
        comp.disciplines.set([discipline])
        self.assertEqual(_payload(self.client, comp)["sport"], "Criterium")

    def test_a_registration_link_becomes_an_offer(self):
        comp = _competition("Open race", url_registration="https://example.com/signup")
        self.assertEqual(_payload(self.client, comp)["offers"]["url"], "https://example.com/signup")

    def test_a_title_carrying_markup_cannot_break_out_of_the_block(self):
        comp = _competition("Race </script><b>x")
        html = self.client.get(comp.get_absolute_url()).content.decode()
        block = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        self.assertNotIn("<b>", block.group(1))
