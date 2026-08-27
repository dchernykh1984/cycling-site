"""What a crawler that does not run scripts sees at /calendar/.

The grid is drawn by FullCalendar after the page loads, so for a long time this page carried
zero links to any event: everything a search engine could see was a `<div id="calendar">`.
"""

import datetime
import re

from django.test import TestCase
from django.urls import reverse

from calendar_app.models import Competition
from locations.models import add_location_child


def _links_outside_scripts(html):
    """Hrefs a crawler can follow -- what is inside `<script>` does not count."""
    without_scripts = re.sub(r"<script.*?</script>", "", html, flags=re.S)
    return re.findall(r'href="([^"]+)"', without_scripts)


class CalendarGridLinksTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        country = add_location_child(None, name="Kazakhstan", name_ru="Kazakhstan")
        region = add_location_child(country, name="Almaty region", name_ru="Almaty region")
        city = add_location_child(region, name="Almaty", name_ru="Almaty")
        cls.venue = add_location_child(city, name="Republic Square", name_ru="Republic Square")
        today = datetime.date.today()
        cls.soon = Competition.objects.create(
            title_ru="Spring race",
            date_start=today + datetime.timedelta(days=3),
            status=Competition.Status.APPROVED,
            location=cls.venue,
        )
        cls.past = Competition.objects.create(
            title_ru="Last year race",
            date_start=today - datetime.timedelta(days=200),
            status=Competition.Status.APPROVED,
            location=cls.venue,
        )
        cls.hidden = Competition.objects.create(
            title_ru="Hidden race",
            date_start=today + datetime.timedelta(days=4),
            status=Competition.Status.APPROVED,
            is_hidden=True,
            location=cls.venue,
        )
        cls.pending = Competition.objects.create(
            title_ru="Unapproved race",
            date_start=today + datetime.timedelta(days=5),
            status=Competition.Status.PENDING_APPROVAL,
            location=cls.venue,
        )

    def _links(self):
        return _links_outside_scripts(self.client.get(reverse("calendar")).content.decode())

    def test_an_upcoming_event_is_linked_from_the_grid_page(self):
        self.assertIn(reverse("competition_detail", args=[self.soon.pk]), self._links())

    def test_the_list_view_is_linked_too(self):
        self.assertIn(reverse("calendar_list"), self._links())

    def test_nothing_unpublished_leaks_into_the_page(self):
        links = self._links()
        for hidden_from_the_public in (self.hidden, self.pending):
            self.assertNotIn(reverse("competition_detail", args=[hidden_from_the_public.pk]), links)

    def test_a_finished_event_is_not_advertised_as_upcoming(self):
        self.assertNotIn(reverse("competition_detail", args=[self.past.pk]), self._links())
