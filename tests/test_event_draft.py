"""A draft another page hands the event form: the virtual ride's "Add event" fills the form, nothing more.

The page posts the event's words in each language, its date and its types and disciplines named in English; the
form opens filled with them for the member to check and submit. Nothing is an event until they do.
"""

import json
import tempfile
from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from calendar_app.models import Competition, Discipline, EventType
from calendar_app.views import _selected_discipline_ids
from locations.models import Location
from trainer.models import GroupRide

DRAFT = {
    "title_ru": "Virtual group race: Old centre",
    "title_kk": "Virtual group race (kk)",
    "title_en": "Virtual group race: Old centre",
    "preview_text_en": "Virtual race Old centre: Tuesday, 2 December, 19:00 (UTC+5)",
    "description_en": '<p>Start at 19:00.</p><script>alert(1)</script><p><a href="https://example.com/">join</a></p>',
    "date_start": "2026-12-02",
    "event_type": ["Virtual Ride", "No such type"],
    "discipline": ["Coffee Ride"],
}


class EventDraftTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.member = User.objects.create_user(
            username="rider", email="r@example.com", password="Pass1234!", role=User.Role.PARTICIPANT
        )
        # the lists as the migrations seed them, which every database has
        cls.coffee = Discipline.objects.get(name_en="Coffee Ride")

    def setUp(self):
        self.client.force_login(self.member)

    def test_the_virtual_ride_is_a_type_of_event_in_every_language(self):
        virtual = EventType.objects.get(name_en="Virtual Ride")
        self.assertTrue(virtual.name_ru and virtual.name_kk)
        # after the types that were there before it, not ahead of the plain race
        self.assertGreater(virtual.order, EventType.objects.get(name_en="Professional Race").order)

    def test_a_draft_opens_the_form_filled_with_it(self):
        response = self.client.post(reverse("calendar_submit_draft"), DRAFT)
        self.assertRedirects(response, reverse("calendar_submit") + "?draft=1")
        form = self.client.get(response["Location"]).context["form"]
        self.assertEqual(form.initial["title_en"], DRAFT["title_en"])
        self.assertEqual(form.initial["preview_text_en"], DRAFT["preview_text_en"])
        self.assertEqual(form.initial["date_start"], "2026-12-02")
        # types and disciplines by their English names, as every database names them; an unknown name is no type
        self.assertEqual(form.initial["event_types"], [EventType.objects.get(name_en="Virtual Ride").pk])
        self.assertEqual(_selected_discipline_ids(form), [self.coffee.pk])

    def test_a_draft_s_description_is_cleaned_as_an_event_s_is(self):
        self.client.post(reverse("calendar_submit_draft"), DRAFT)
        description = self.client.get(reverse("calendar_submit") + "?draft=1").context["form"].initial["description_en"]
        self.assertNotIn("<script", description)
        self.assertIn('href="https://example.com/"', description)

    def test_the_form_is_empty_unless_its_address_asks_for_the_draft(self):
        self.client.post(reverse("calendar_submit_draft"), DRAFT)
        self.assertNotIn("title_en", self.client.get(reverse("calendar_submit")).context["form"].initial)

    def test_a_date_no_calendar_has_is_left_for_the_form_to_ask(self):
        self.client.post(reverse("calendar_submit_draft"), {**DRAFT, "date_start": "2026-02-30"})
        self.assertNotIn("date_start", self.client.get(reverse("calendar_submit") + "?draft=1").context["form"].initial)

    def test_nothing_is_an_event_until_it_is_submitted_and_then_the_draft_is_gone(self):
        self.client.post(reverse("calendar_submit_draft"), DRAFT)
        self.assertFalse(Competition.objects.exists())
        self.client.post(reverse("calendar_submit"), {"title_ru": "Virtual race", "date_start": "2026-12-02"})
        self.assertTrue(Competition.objects.filter(title_ru="Virtual race").exists())
        self.assertNotIn("title_en", self.client.get(reverse("calendar_submit") + "?draft=1").context["form"].initial)

    def test_a_reader_who_is_not_signed_in_is_asked_to_sign_in(self):
        self.client.logout()
        response = self.client.post(reverse("calendar_submit_draft"), DRAFT)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("account_login"), response["Location"])


#: A route's track as the virtual ride sends it: three points of the old centre
GPX = (
    '<?xml version="1.0" encoding="UTF-8"?><gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">'
    '<trk><name>Old centre</name><trkseg><trkpt lat="43.2380" lon="76.9450"><ele>800</ele></trkpt>'
    '<trkpt lat="43.2390" lon="76.9460"><ele>805</ele></trkpt><trkpt lat="43.2400" lon="76.9470"><ele>810</ele></trkpt>'
    "</trkseg></trk></gpx>"
)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class VirtualRaceDraftTests(TestCase):
    """The virtual ride's "Add event" also brings the venue at its route's start, a race's registration with its
    categories, the route's track and the race the event is to hold -- taken only by the form its draft opened."""

    @classmethod
    def setUpTestData(cls):
        cls.organizer = User.objects.create_user(
            username="org", email="org@example.com", password="Pass1234!", role=User.Role.ORGANIZER
        )
        city = (
            Location.add_root(name_ru="KZ", name_en="KZ")
            .add_child(name_ru="Region", name_en="Region")
            .add_child(name_ru="City", name_en="City")
        )
        cls.start = city.add_child(name_ru="Start", name_en="Start", lat=43.2380, lng=76.9450)
        city.add_child(name_ru="Far", name_en="Far", lat=43.2600, lng=76.9450)  # 2.4 km on

    def setUp(self):
        self.client.force_login(self.organizer)

    def race(self, host=None, kind=GroupRide.Kind.RACE):
        start = timezone.now() + timedelta(days=3)
        return GroupRide.objects.create(route="oldtown", host=host or self.organizer, kind=kind, start_at=start)

    def draft(self, **extra):
        return self.client.post(reverse("calendar_submit_draft"), {**DRAFT, **extra})

    def form_page(self):
        return self.client.get(reverse("calendar_submit") + "?draft=1")

    def submit(self, key, title="Virtual race"):
        payload = {"title_ru": title, "date_start": "2026-12-02", "location": str(self.start.pk), "draft_key": key}
        return self.client.post(reverse("calendar_submit"), payload)

    def test_the_venue_at_the_route_s_start_is_chosen_and_none_further_than_300_m(self):
        self.draft(start_lat="43.2381", start_lng="76.9452")
        self.assertEqual(self.form_page().context["form"]["location"].value(), self.start.pk)
        self.draft(start_lat="43.2490", start_lng="76.9450")  # 1.2 km from either
        self.assertIsNone(self.form_page().context["form"]["location"].value())

    def test_a_race_s_registration_comes_on_with_its_categories(self):
        rows = [
            {"name": "Men", "male": True, "female": False, "laps": 3},
            {"name": "Women", "male": False, "female": True, "laps": 3},
            {"name": " "},
            "not a row",
        ]
        self.draft(registration="1", categories=json.dumps(rows))
        page = self.form_page()
        self.assertTrue(page.context["reg_form"].initial["registration_enabled"])
        shown = [(r["name"], r["male"], r["female"], r["laps"]) for r in json.loads(page.context["categories_json"])]
        self.assertEqual(shown, [("Men", True, False, 3), ("Women", False, True, 3)])

    def test_the_route_s_track_is_attached_unless_the_member_chose_a_file(self):
        self.draft(track_name="oldtown", track_gpx=GPX)
        page = self.form_page()
        self.assertContains(page, 'id="route-draft-track"')
        self.submit(page.context["draft_key"])
        event = Competition.objects.get(title_ru="Virtual race")
        self.assertTrue(event.file_route.name.endswith("oldtown.gpx"), event.file_route.name)
        self.assertEqual(event.file_route.read().decode(), GPX)

    def test_what_holds_no_track_is_not_attached(self):
        self.draft(track_name="oldtown", track_gpx="<gpx>nothing to draw</gpx>")
        self.assertFalse(self.form_page().context["draft_track"])

    def test_the_race_is_held_by_the_event_made_from_its_draft(self):
        race = self.race()
        self.draft(virtual_race=str(race.pk), registration="1")
        self.submit(self.form_page().context["draft_key"])
        race.refresh_from_db()
        self.assertEqual(race.competition, Competition.objects.get(title_ru="Virtual race"))

    def test_a_form_opened_otherwise_takes_nothing_of_a_draft_left_over(self):
        race = self.race()
        self.draft(virtual_race=str(race.pk), track_name="oldtown", track_gpx=GPX)
        self.submit("")  # the form opened by hand later sends no key
        race.refresh_from_db()
        self.assertIsNone(race.competition)
        self.assertFalse(Competition.objects.get(title_ru="Virtual race").file_route)

    def test_someone_else_s_race_or_a_ride_is_held_by_no_event(self):
        other = User.objects.create_user(
            username="other", email="other@example.com", password="Pass1234!", role=User.Role.ORGANIZER
        )
        for race in (self.race(host=other), self.race(kind=GroupRide.Kind.RIDE)):
            self.draft(virtual_race=str(race.pk))
            self.submit(self.form_page().context["draft_key"], title=f"Virtual race {race.pk}")
            race.refresh_from_db()
            self.assertIsNone(race.competition)
