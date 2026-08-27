"""The calendar as a subscription.

`/calendar/calendar.ics` is what a phone calendar polls, so the bytes have to satisfy a parser
rather than a reader: CRLF line endings, folded long lines, escaped separators, and an all-day
event whose DTEND is the day after the last one.
"""

import datetime

from django.test import TestCase
from django.urls import reverse

from calendar_app.models import Competition, Discipline, DisciplineCategory
from locations.models import add_location_child

TODAY = datetime.date.today()


def _events(body):
    """Unfold the continuation lines, then split into VEVENT blocks."""
    unfolded = body.replace("\r\n ", "")
    blocks = unfolded.split("BEGIN:VEVENT")[1:]
    return [block.split("END:VEVENT")[0].strip().splitlines() for block in blocks]


def _field(lines, name):
    """The value of one property, ignoring any parameters after a semicolon in its name."""
    for line in lines:
        prop, _, value = line.partition(":")
        if prop.split(";")[0] == name:
            return value
    return None


class ICSFeedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        country = add_location_child(None, name="Kazakhstan", name_ru="Kazakhstan")
        region = add_location_child(country, name="Almaty region", name_ru="Almaty region")
        cls.city = add_location_child(region, name="Almaty", name_ru="Almaty")
        cls.venue = add_location_child(cls.city, name="Republic Square", name_ru="Republic Square")
        other_country = add_location_child(None, name="Kyrgyzstan", name_ru="Kyrgyzstan")
        other_region = add_location_child(other_country, name="Chuy", name_ru="Chuy")
        other_city = add_location_child(other_region, name="Bishkek", name_ru="Bishkek")
        cls.other_venue = add_location_child(other_city, name="Ala-Too", name_ru="Ala-Too")

        category = DisciplineCategory.objects.create(name_ru="Road", name_en="Road", order=1)
        cls.discipline = Discipline.objects.create(name_ru="Criterium", name_en="Criterium", category=category, order=1)
        cls.stage_race = Competition.objects.create(
            title_ru="Tour of Almaty; the long, hard one",
            date_start=TODAY + datetime.timedelta(days=10),
            date_end=TODAY + datetime.timedelta(days=12),
            status=Competition.Status.APPROVED,
            location=cls.venue,
        )
        cls.stage_race.disciplines.set([cls.discipline])
        cls.one_day = Competition.objects.create(
            title_ru="Bishkek criterium",
            date_start=TODAY + datetime.timedelta(days=11),
            status=Competition.Status.APPROVED,
            location=cls.other_venue,
        )
        Competition.objects.create(
            title_ru="Hidden race",
            date_start=TODAY + datetime.timedelta(days=13),
            status=Competition.Status.APPROVED,
            is_hidden=True,
            location=cls.venue,
        )
        Competition.objects.create(
            title_ru="Ancient race",
            date_start=TODAY - datetime.timedelta(days=400),
            status=Competition.Status.APPROVED,
            location=cls.venue,
        )

    def _body(self, **params):
        response = self.client.get(reverse("calendar_ics"), params)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/calendar"))
        return response.content.decode()

    def test_it_is_a_calendar_a_client_will_accept(self):
        body = self._body()
        self.assertTrue(body.startswith("BEGIN:VCALENDAR\r\n"))
        self.assertTrue(body.rstrip().endswith("END:VCALENDAR"))
        self.assertIn("VERSION:2.0", body)
        self.assertNotIn("\n\n", body)
        for line in body.split("\r\n"):
            self.assertLessEqual(len(line.encode()), 75, line)

    def test_a_multi_day_event_ends_the_day_after_its_last_one(self):
        """All-day DTEND is exclusive -- off by one and the last day drops out of the phone."""
        lines = next(e for e in _events(self._body()) if "Tour of Almaty" in _field(e, "SUMMARY"))
        self.assertEqual(_field(lines, "DTSTART"), f"{self.stage_race.date_start:%Y%m%d}")
        self.assertEqual(_field(lines, "DTEND"), f"{self.stage_race.date_end + datetime.timedelta(days=1):%Y%m%d}")

    def test_a_one_day_event_still_declares_an_end(self):
        lines = next(e for e in _events(self._body()) if "Bishkek" in _field(e, "SUMMARY"))
        self.assertEqual(_field(lines, "DTEND"), f"{self.one_day.date_start + datetime.timedelta(days=1):%Y%m%d}")

    def test_a_separator_in_a_title_is_escaped_not_dropped(self):
        lines = next(e for e in _events(self._body()) if "Tour of Almaty" in _field(e, "SUMMARY"))
        self.assertIn("\\;", _field(lines, "SUMMARY"))
        self.assertIn("\\,", _field(lines, "SUMMARY"))

    def test_every_event_links_back_to_its_page(self):
        for lines in _events(self._body()):
            self.assertIn(reverse("competition_detail", args=[1]).rsplit("/", 2)[0], _field(lines, "URL"))

    def test_it_carries_the_same_filters_as_the_list(self):
        filtered = self._body(location=self.city.pk)
        self.assertIn("Tour of Almaty", filtered)
        self.assertNotIn("Bishkek criterium", filtered)

    def test_nothing_hidden_or_long_finished_is_published(self):
        body = self._body()
        self.assertNotIn("Hidden race", body)
        self.assertNotIn("Ancient race", body)
