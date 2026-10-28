"""Which events a period holds in the list and on the map (issue #352).

The calendar's grid shows an event on every day it runs. The list and the map used to take only the
events that started inside the period, so a race from Friday to Sunday was missing from the weekend
and a race that began last week dropped out while it was still on.
"""

import datetime
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from calendar_app.models import Competition
from locations.models import add_location_child

DAY = datetime.timedelta(days=1)
TODAY = timezone.localdate()
# A Saturday at least a week ahead, so every event below is still to come
SATURDAY = TODAY + datetime.timedelta(days=(5 - TODAY.weekday()) % 7 + 7)
WEEKEND = {"date_from": SATURDAY.isoformat(), "date_to": (SATURDAY + DAY).isoformat()}


def _event(title, start, end=None, location=None):
    return Competition.objects.create(
        title_ru=title, date_start=start, date_end=end, status=Competition.Status.APPROVED, location=location
    )


class PeriodTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        country = add_location_child(None, name="Kazakhstan", name_ru="Kazakhstan")
        region = add_location_child(country, name="Almaty region", name_ru="Almaty region")
        city = add_location_child(region, name="Almaty", name_ru="Almaty", lat=Decimal("43.2"), lng=Decimal("76.9"))
        venue = add_location_child(city, name="Medeu", name_ru="Medeu")
        _event("Friday to Sunday", SATURDAY - DAY, SATURDAY + DAY, venue)
        _event("All week", SATURDAY - 6 * DAY, SATURDAY + DAY, venue)
        _event("Saturday", SATURDAY, None, venue)
        _event("Friday only", SATURDAY - DAY, None, venue)
        _event("Next Monday", SATURDAY + 2 * DAY, None, venue)

    def _list(self, params):
        return {c.title for c in self.client.get(reverse("calendar_list"), params).context["competitions"]}

    def _map(self, params):
        groups = self.client.get(reverse("calendar_map_api"), params).json()
        return {c["title"] for group in groups for c in group["competitions"]}

    def test_the_weekend_holds_every_event_that_runs_on_it(self):
        held = {"Friday to Sunday", "All week", "Saturday"}
        self.assertEqual(self._list(WEEKEND), held)
        self.assertEqual(self._map(WEEKEND), held)

    def test_the_default_list_holds_an_event_still_running_and_not_one_already_over(self):
        _event("Ongoing", TODAY - 2 * DAY, TODAY + DAY)
        _event("Over", TODAY - 3 * DAY, TODAY - DAY)
        titles = self._list({})
        self.assertIn("Ongoing", titles)
        self.assertNotIn("Over", titles)
