"""The list's place column (issue #383): venue, city, region and country in one, each named once.

Four columns of them left too little room on a desktop, and the table broke its headings and dates
in the middle of a word.
"""

import datetime
import re

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from calendar_app.models import Competition
from locations.models import Location, add_location_child

DAY = timezone.localdate() + datetime.timedelta(days=3)


def _places(html):
    """Each row's place as the reader reads it, and the venue the cell sets apart for a skin."""
    cells = re.findall(r'<td data-label="[^"]*">(<span class="place-venue">.*?)</td>', html)
    return [(re.sub(r"<[^>]+>", "", cell), re.search(r'place-venue">([^<]*)<', cell).group(1)) for cell in cells]


class PlaceColumnTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        country = add_location_child(None, name="Kazakhstan", name_ru="Kazakhstan")
        region = add_location_child(country, name="Almaty region", name_ru="Almaty region")
        cls.city = add_location_child(region, name="Almaty", name_ru="Almaty")
        cls.venue = add_location_child(cls.city, name="Medeu", name_ru="Medeu")

    def _list(self):
        return self.client.get(reverse("calendar_list"), {"date_to": (DAY + datetime.timedelta(days=1)).isoformat()})

    def test_the_place_reads_from_the_start_point_out(self):
        Competition.objects.create(title_ru="At Medeu", date_start=DAY, status="approved", location=self.venue)
        places = _places(self._list().content.decode())
        self.assertEqual(places, [("Medeu, Almaty, Almaty region, Kazakhstan", "Medeu")])

    def test_a_start_point_not_yet_known_names_its_city_once(self):
        catch_all = Location.get_or_create_other_location(self.city)
        Competition.objects.create(title_ru="Somewhere", date_start=DAY, status="approved", location=catch_all)
        self.assertEqual(_places(self._list().content.decode()), [("Almaty, Almaty region, Kazakhstan", "Almaty")])
