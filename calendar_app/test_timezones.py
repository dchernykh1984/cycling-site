"""An event's time zone comes from its place, a reader's from their browser (issue #344)."""

import datetime
import re
from unittest import mock
from zoneinfo import ZoneInfo

from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from calendar_app.models import Competition
from cycling_site.middleware import ReaderTimezoneMiddleware
from locations.models import Location, timezone_of

TOKYO = ZoneInfo("Asia/Tokyo")


def _tree():
    """A country with a point, a region and a city without one, and a venue in Tokyo."""
    country = Location.add_root(name_ru="Japan", name_en="Japan", lat="35.689500", lng="139.691700")
    region = country.add_child(name_ru="Kanto", name_en="Kanto")
    city = region.add_child(name_ru="Tokyo", name_en="Tokyo")
    venue = city.add_child(name_ru="Park", name_en="Park", lat="35.689500", lng="139.691700")
    return country, region, city, venue


class TimezoneOfTests(TestCase):
    def test_a_place_with_coordinates_has_their_zone(self):
        *_, venue = _tree()
        self.assertEqual(timezone_of(venue), TOKYO)

    def test_a_place_without_coordinates_takes_the_nearest_ancestor_with_them(self):
        _, _, city, _ = _tree()
        bare = city.add_child(name_ru="Bare", name_en="Bare")
        with self.assertNumQueries(1):
            self.assertEqual(timezone_of(bare), TOKYO)

    def test_the_nearest_ancestor_wins_over_one_further_up(self):
        country = Location.add_root(name_ru="C", name_en="C", lat="51.507400", lng="-0.127800")
        city = country.add_child(name_ru="City", name_en="City", lat="35.689500", lng="139.691700")
        venue = city.add_child(name_ru="V", name_en="V")
        self.assertEqual(timezone_of(venue), TOKYO)

    def test_no_coordinates_anywhere_up_the_chain_is_utc(self):
        country = Location.add_root(name_ru="Nowhere", name_en="Nowhere")
        venue = country.add_child(name_ru="V", name_en="V")
        self.assertEqual(timezone_of(venue), ZoneInfo("UTC"))
        self.assertEqual(timezone_of(None), ZoneInfo("UTC"))

    def test_the_event_takes_the_zone_of_its_place(self):
        *_, venue = _tree()
        comp = Competition(title_ru="R", date_start=datetime.date(2026, 9, 1), location=venue)
        self.assertEqual(comp.timezone, TOKYO)


class RegistrationClosesByTheEventsDayTests(TestCase):
    def _open_without_deadline(self, location, now):
        comp = Competition.objects.create(
            title_ru="R",
            date_start=datetime.date(2026, 9, 1),
            status=Competition.Status.APPROVED,
            registration_enabled=True,
            location=location,
        )
        with mock.patch("django.utils.timezone.now", return_value=now):
            return comp.is_registration_open()

    def test_the_last_day_ends_at_midnight_at_the_place(self):
        *_, venue = _tree()
        # 16:00 UTC on the 1st is already 01:00 on the 2nd in Tokyo.
        late = datetime.datetime(2026, 9, 1, 16, 0, tzinfo=datetime.UTC)
        self.assertFalse(self._open_without_deadline(venue, late))
        self.assertTrue(self._open_without_deadline(venue, late - datetime.timedelta(hours=2)))

    def test_an_event_in_another_zone_is_still_on_its_last_day(self):
        nowhere = Location.add_root(name_ru="Nowhere", name_en="Nowhere")
        # 20:00 UTC on the 1st is the 2nd in the site's default zone, but still the 1st in UTC.
        self.assertTrue(self._open_without_deadline(nowhere, datetime.datetime(2026, 9, 1, 20, 0, tzinfo=datetime.UTC)))


class DeadlineTypedInTheEventsZoneTests(TestCase):
    def setUp(self):
        *_, self.venue = _tree()
        self.organizer = User.objects.create_user(
            username="tz_org@example.com", email="tz_org@example.com", role=User.Role.ORGANIZER
        )
        self.client.force_login(self.organizer)
        # The organizer's browser is in Moscow; the race is in Tokyo.
        self.client.cookies["tz"] = "Europe/Moscow"

    def _payload(self, **extra):
        return {
            "title_ru": "Tokyo Race",
            "date_start": "2026-09-01",
            "location": str(self.venue.pk),
            "registration_enabled": "on",
            "registration_mode": "free",
            "birth_date_mode": "year",
            "registration_deadline": "2026-09-01T14:30",
            "categories_json": "[]",
            **extra,
        }

    def _assert_tokyo_1430(self, comp):
        self.assertEqual(comp.registration_deadline, datetime.datetime(2026, 9, 1, 14, 30, tzinfo=TOKYO))

    def test_submit_reads_the_deadline_in_the_events_zone(self):
        self.client.post(reverse("calendar_submit"), self._payload())
        self._assert_tokyo_1430(Competition.objects.get(title_ru="Tokyo Race"))

    def test_edit_reads_the_deadline_in_the_zone_of_the_new_place(self):
        comp = Competition.objects.create(
            title_ru="Tokyo Race",
            date_start=datetime.date(2026, 9, 1),
            status=Competition.Status.APPROVED,
            submitted_by=self.organizer,
        )
        self.client.post(reverse("competition_edit", args=[comp.pk]), self._payload())
        comp.refresh_from_db()
        self._assert_tokyo_1430(comp)

    def test_edit_form_shows_the_deadline_as_typed(self):
        comp = Competition.objects.create(
            title_ru="Tokyo Race",
            date_start=datetime.date(2026, 9, 1),
            status=Competition.Status.APPROVED,
            submitted_by=self.organizer,
            location=self.venue,
            registration_enabled=True,
            registration_deadline=datetime.datetime(2026, 9, 1, 14, 30, tzinfo=TOKYO),
        )
        html = self.client.get(reverse("competition_edit", args=[comp.pk])).content.decode()
        self.assertEqual(
            re.search(r'name="registration_deadline"[^>]*value="([^"]*)"', html).group(1), "2026-09-01T14:30"
        )


class ReaderTimezoneMiddlewareTests(TestCase):
    def _zone_for(self, cookie):
        seen = {}

        def view(request):
            seen["zone"] = timezone.get_current_timezone_name()
            return HttpResponse()

        request = RequestFactory().get("/")
        if cookie is not None:
            request.COOKIES["tz"] = cookie
        ReaderTimezoneMiddleware(view)(request)
        timezone.deactivate()
        return seen["zone"]

    def test_the_browsers_zone_is_activated(self):
        self.assertEqual(self._zone_for("America/Argentina/Buenos_Aires"), "America/Argentina/Buenos_Aires")

    def test_no_or_a_bad_zone_leaves_the_sites_default(self):
        default = timezone.get_default_timezone_name()
        for cookie in (None, "", "Nope/Zone", "../../etc/passwd", "zone.tab"):
            with self.subTest(cookie=cookie):
                self.assertEqual(self._zone_for(cookie), default)

    def test_a_reader_sees_a_comment_time_in_their_zone(self):
        from calendar_app.models import CompetitionComment

        author = User.objects.create_user(username="c@example.com", email="c@example.com")
        comp = Competition.objects.create(
            title_ru="R", date_start=datetime.date(2026, 9, 1), status=Competition.Status.APPROVED
        )
        comment = CompetitionComment.objects.create(competition=comp, author=author, body="hi")
        CompetitionComment.objects.filter(pk=comment.pk).update(
            created_at=datetime.datetime(2026, 9, 1, 12, 0, tzinfo=datetime.UTC)
        )
        self.client.cookies["tz"] = "Asia/Tokyo"
        html = self.client.get(reverse("competition_detail", args=[comp.pk])).content.decode()
        self.assertIn("01.09.2026 21:00", html)
