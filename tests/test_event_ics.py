"""One event's calendar file (issue #398).

`/<lang>/calendar/<id>/event.ics` is what "Add to calendar" on an event's page hands the reader's own
calendar: the subscription's entry for that one event, in the page's language, answering exactly
the people the page answers.
"""

import datetime
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import override as translation_override

from accounts.models import User
from calendar_app.models import Competition, CompetitionInvite
from locations.models import Location, add_location_child
from tests.language_urls import in_language
from tests.test_ics_feed import _events, _field

DAY = timezone.localdate() + datetime.timedelta(days=20)


def _user(name, role):
    return User.objects.create_user(username=name, email=f"{name}@example.com", password="pw", role=role)


def _event(**kwargs):
    defaults = {
        "title_ru": "Gonka",
        "title_kk": "Zharys",
        "date_start": DAY,
        "status": Competition.Status.APPROVED,
        "approved_at": timezone.now(),
    }
    return Competition.objects.create(**{**defaults, **kwargs})


class EventFileTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        country = add_location_child(None, name="Kazakhstan", name_ru="Kazakhstan")
        region = add_location_child(country, name="Almaty region", name_ru="Almaty region")
        cls.city = add_location_child(region, name="Almaty", name_ru="Almaty", lat=Decimal("43.2"), lng=Decimal("76.9"))
        cls.venue = add_location_child(
            cls.city, name="Medeu", name_ru="Medeu", lat=Decimal("43.157496"), lng=Decimal("77.059023")
        )
        cls.race = _event(location=cls.venue, date_end=DAY + datetime.timedelta(days=2))

    def _file(self, competition, language="ru"):
        return self.client.get(in_language(reverse("competition_ics", args=[competition.pk]), language))

    def test_it_is_the_one_event_all_day_from_its_first_day_to_the_day_after_its_last(self):
        response = self._file(self.race)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/calendar; charset=utf-8")
        self.assertIn(f'filename="event-{self.race.pk}.ics"', response["Content-Disposition"])
        [lines] = _events(response.content.decode())
        self.assertEqual(_field(lines, "DTSTART"), f"{DAY:%Y%m%d}")
        self.assertEqual(_field(lines, "DTEND"), f"{DAY + datetime.timedelta(days=3):%Y%m%d}")
        self.assertEqual(_field(lines, "LOCATION"), "Medeu")

    def test_it_speaks_the_language_of_its_address(self):
        [lines] = _events(self._file(self.race, "kk").content.decode())
        self.assertEqual(_field(lines, "SUMMARY"), "Zharys")
        self.assertTrue(_field(lines, "URL").endswith(f"/kk/calendar/{self.race.pk}/"), _field(lines, "URL"))

    def test_it_carries_the_venue_s_own_point(self):
        [lines] = _events(self._file(self.race).content.decode())
        self.assertEqual(_field(lines, "GEO"), "43.157496;77.059023")

    def test_a_city_s_point_is_not_handed_out_as_the_start(self):
        catch_all = Location.get_or_create_other_location(self.city)
        Location.objects.filter(pk=catch_all.pk).update(lat=Decimal("43.2"), lng=Decimal("76.9"))
        nowhere = add_location_child(self.city, name="Somewhere", name_ru="Somewhere")
        for location in (catch_all, nowhere):
            [lines] = _events(self._file(_event(location=location)).content.decode())
            self.assertIsNone(_field(lines, "GEO"), location)

    def test_search_engines_are_told_to_keep_to_the_page(self):
        self.assertEqual(self._file(self.race)["X-Robots-Tag"], "noindex")


class WhoGetsTheFileTests(TestCase):
    """The page's own rule: whoever may open the page gets its file, everybody else a 404."""

    @classmethod
    def setUpTestData(cls):
        cls.author = _user("author", User.Role.ORGANIZER)
        cls.admin = _user("admin", User.Role.ADMIN)
        cls.invitee = _user("invitee", User.Role.PARTICIPANT)
        cls.stranger = _user("stranger", User.Role.PARTICIPANT)

    def _status(self, competition, user=None):
        if user is not None:
            self.client.force_login(user)
        status = self.client.get(reverse("competition_ics", args=[competition.pk])).status_code
        page = self.client.get(reverse("competition_detail", args=[competition.pk])).status_code
        self.assertEqual(status, page, "the file and the page disagree")
        self.client.logout()
        return status

    def test_an_event_awaiting_review_is_its_author_s_and_its_moderators(self):
        pending = _event(status=Competition.Status.PENDING_APPROVAL, approved_at=None, submitted_by=self.author)
        self.assertEqual(self._status(pending), 404)
        self.assertEqual(self._status(pending, self.stranger), 404)
        self.assertEqual(self._status(pending, self.author), 200)
        self.assertEqual(self._status(pending, self.admin), 200)

    def test_a_hidden_event_is_its_managers(self):
        hidden = _event(is_hidden=True, submitted_by=self.author)
        self.assertEqual(self._status(hidden), 404)
        self.assertEqual(self._status(hidden, self.stranger), 404)
        self.assertEqual(self._status(hidden, self.admin), 200)

    def test_an_invite_only_event_is_for_the_people_let_in(self):
        private = _event(invite_only=True, submitted_by=self.author)
        CompetitionInvite.objects.create(competition=private, user=self.invitee)
        self.assertEqual(self._status(private), 404)
        self.assertEqual(self._status(private, self.stranger), 404)
        self.assertEqual(self._status(private, self.invitee), 200)
        self.assertEqual(self._status(private, self.author), 200)

    def test_a_deleted_event_is_nobody_s(self):
        gone = _event(is_deleted=True, submitted_by=self.author)
        self.assertEqual(self._status(gone, self.admin), 404)


class ButtonTests(TestCase):
    """ "Add to calendar" beside "Share" on a published event's page, leading to its file."""

    @classmethod
    def setUpTestData(cls):
        cls.author = _user("author", User.Role.ORGANIZER)

    def test_a_published_event_offers_its_file_in_the_page_s_language(self):
        race = _event(submitted_by=self.author)
        page = reverse("competition_detail", args=[race.pk])
        for language in ("ru", "kk", "en"):
            html = self.client.get(in_language(page, language)).content.decode()
            with translation_override(language):
                self.assertIn(f'aria-label="{gettext("Add to calendar")}"', html, language)
            self.assertIn(f'href="/{language}/calendar/{race.pk}/event.ics"', html, language)

    def test_an_event_awaiting_review_offers_none_even_to_its_author(self):
        pending = _event(status=Competition.Status.PENDING_APPROVAL, approved_at=None, submitted_by=self.author)
        self.client.force_login(self.author)
        response = self.client.get(reverse("competition_detail", args=[pending.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "calendar-btn")
