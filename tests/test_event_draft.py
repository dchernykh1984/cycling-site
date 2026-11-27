"""A draft another page hands the event form: the virtual ride's calendar box fills the form, nothing more.

The page posts the event's words in each language, its date and its types and disciplines named in English; the
form opens filled with them for the member to check and submit. Nothing is an event until they do.
"""

import io
import json
import tempfile
import uuid
from datetime import timedelta
from unittest import mock

from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext
from PIL import Image

from accounts.models import User
from calendar_app import ride_picture
from calendar_app.models import Competition, Discipline, EventType
from calendar_app.views import _selected_discipline_ids
from locations.models import Location, LocationProposal
from trainer.models import GroupRide, GroupRideMember

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
        key = self.client.get(reverse("calendar_submit") + "?draft=1").context["draft_key"]
        submitted = {"title_ru": "Virtual race", "date_start": "2026-12-02", "draft_key": key}
        self.client.post(reverse("calendar_submit"), submitted)
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


# the lines of the ride's picture, as the virtual ride's page writes them in its language
PICTURE = {
    "picture_route": "oldtown",
    "picture_when": "Tue, 2 December \u00b7 19:00 (UTC+5)",
    "picture_title": "Virtual race: Old centre",
    "picture_facts": "4.5 km, 63 m of climbing",
}


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class VirtualRaceDraftTests(TestCase):
    """The virtual ride's calendar box also brings the venue at its route's start, a race's registration with its
    categories, the route's track and the race the event is to hold -- taken only by the form its draft opened."""

    @classmethod
    def setUpTestData(cls):
        cls.organizer = User.objects.create_user(
            username="org", email="org@example.com", password="Pass1234!", role=User.Role.ORGANIZER
        )
        cls.city = (
            Location.add_root(name_ru="KZ", name_en="KZ")
            .add_child(name_ru="Region", name_en="Region")
            .add_child(name_ru="City", name_en="City", lat=43.2500, lng=76.9300)
        )
        # a real place at the route's start: a virtual ride's event never takes it for its meeting point
        cls.start = cls.city.add_child(name_ru="Start", name_en="Start", lat=43.2380, lng=76.9450)

    def setUp(self):
        self.client.force_login(self.organizer)

    def race(self, host=None, kind=GroupRide.Kind.RACE):
        start = timezone.now() + timedelta(days=3)
        return GroupRide.objects.create(route="oldtown", host=host or self.organizer, kind=kind, start_at=start)

    def draft(self, **extra):
        return self.client.post(reverse("calendar_submit_draft"), {**DRAFT, **extra})

    def form_page(self):
        return self.client.get(reverse("calendar_submit") + "?draft=1")

    def submit(self, key, title="Virtual race", registers=False, day="2026-12-02"):
        payload = {"title_ru": title, "date_start": day, "location": str(self.start.pk), "draft_key": key}
        if registers:  # registration on the site, as a race's draft ticks it
            payload["registration_enabled"] = "on"
        return self.client.post(reverse("calendar_submit"), payload)

    def chosen(self, **extra):
        start = {"start_lat": "43.2381", "start_lng": "76.9452"}
        self.draft(**start, route_name_ru="Staryi tsentr", route_name_en="Old centre", **extra)
        return self.form_page().context["form"]["location"].value()

    def test_a_route_s_start_becomes_its_venue_in_the_virtual_world_once(self):
        venue = Location.objects.get(pk=self.chosen())
        self.assertNotEqual(venue.pk, self.start.pk)
        # named so in every language that nobody comes to the place to meet
        self.assertEqual(venue.name_en, 'Virtual world: start of the route "Old centre"')
        with translation.override("ru"):
            self.assertEqual(
                venue.name_ru, gettext('Virtual world: start of the route "%(route)s"') % {"route": "Staryi tsentr"}
            )
        # where the route starts, under its city, public at once for an organizer
        self.assertEqual((float(venue.lat), float(venue.lng)), (43.2381, 76.9452))
        self.assertEqual(venue.get_parent(), self.city)
        self.assertFalse(LocationProposal.objects.filter(location=venue).exists())
        # the next event on that route finds it: one venue for the route's start
        self.assertEqual(self.chosen(), venue.pk)
        self.assertEqual(Location.objects.filter(name_en=venue.name_en).count(), 1)

    def test_a_participant_s_draft_proposes_the_start_for_review(self):
        rider = User.objects.create_user(
            username="rider2", email="rider2@example.com", password="Pass1234!", role=User.Role.PARTICIPANT
        )
        self.client.force_login(rider)
        venue = Location.objects.get(pk=self.chosen())
        self.assertTrue(LocationProposal.objects.filter(location=venue, submitted_by=rider).exists())

    def test_a_start_renamed_or_deleted_is_made_again(self):
        first = Location.objects.get(pk=self.chosen())
        first.name_ru = "Renamed by a moderator"
        first.save(update_fields=["name_ru"])
        second = self.chosen()
        self.assertNotEqual(second, first.pk)
        Location.objects.filter(pk=second).update(is_deleted=True)
        self.assertNotIn(self.chosen(), (first.pk, second))

    def test_a_start_far_from_every_city_has_no_venue(self):
        self.draft(start_lat="44.5", start_lng="78.9", route_name_ru="Staryi tsentr")
        self.assertIsNone(self.form_page().context["form"]["location"].value())
        self.draft(start_lat="43.2381", start_lng="76.9452")  # no route's name to give it
        self.assertIsNone(self.form_page().context["form"]["location"].value())

    def test_a_race_s_registration_comes_on_with_its_categories_and_settings(self):
        year = timezone.localdate().year
        men = {"name": "Men", "male": True, "female": False, "laps": 3, "birth_from": 1900, "birth_to": year}
        women = {**men, "name": "Women", "male": False, "female": True}
        rows = [
            {**men, "bib_from": 100, "bib_to": 999, "max_participants": 900},
            {**women, "bib_from": 1, "bib_to": 99, "max_participants": 99},
            {"name": "Out of range", "laps": 0, "birth_from": 1800, "bib_from": -5, "max_participants": True},
            {"name": " "},
            "not a row",
        ]
        settings = {
            "birth_date_mode": "year",
            "max_participants": "999",
            "additional_info_mode": "strava",
            "additional_info_label": "Strava link",
            "show_additional_info_in_list": "1",
            "additional_info_required": "1",
        }
        self.draft(registration="1", categories=json.dumps(rows), **settings)
        page = self.form_page()
        initial = page.context["reg_form"].initial
        self.assertEqual(
            {k: initial.get(k) for k in ["registration_enabled", *settings]},
            {
                "registration_enabled": True,
                "birth_date_mode": "year",
                "max_participants": 999,
                "additional_info_mode": "strava",
                "additional_info_label": "Strava link",
                "show_additional_info_in_list": True,
                "additional_info_required": True,
            },
        )
        keys = ("name", "male", "female", "birth_from", "birth_to", "laps", "bib_from", "bib_to", "max_participants")
        shown = [tuple(r[k] for k in keys) for r in json.loads(page.context["categories_json"])]
        self.assertEqual(
            shown,
            [
                ("Men", True, False, "1900", str(year), 3, 100, 999, 900),
                ("Women", False, True, "1900", str(year), 3, 1, 99, 99),
                ("Out of range", False, False, None, None, None, None, None, None),
            ],
        )
        # a setting the form refuses is left to its default
        self.draft(registration="1", additional_info_mode="no such mode", max_participants="-3")
        initial = self.form_page().context["reg_form"].initial
        self.assertNotIn("additional_info_mode", initial)
        self.assertNotIn("max_participants", initial)

    def test_the_event_opens_the_ride_it_is_ridden_in_and_nobody_types_it(self):
        ride = self.race(kind=GroupRide.Kind.RIDE)
        self.draft(virtual_ride=str(ride.pk))
        page = self.form_page()
        link = f"{reverse('virtual_ride')}?group={ride.pk}"
        # the form shows it, as a link, not as a field to type into
        self.assertContains(page, 'id="virtual-ride-field"')
        self.assertContains(page, f'href="{link}"')
        self.assertNotContains(page, 'name="virtual_ride"')
        self.submit(page.context["draft_key"])
        event = Competition.objects.get(title_ru="Virtual race")
        self.assertEqual(event.virtual_ride, ride.pk)
        # the event's page goes to it, in the reader's language -- not "open the ride", which reads as starting it;
        # a ride is held by no event's protocol
        shown = self.client.get(event.get_absolute_url())
        self.assertContains(shown, f'href="{link}"')
        with translation.override("ru"):
            self.assertContains(shown, gettext("Go to the virtual ride"))
        ride.refresh_from_db()
        self.assertIsNone(ride.competition)
        # its edit page shows it, and neither its form nor the API takes another: a change to the event keeps it
        edit = self.client.get(reverse("competition_edit", args=[event.pk]))
        self.assertContains(edit, 'id="virtual-ride-field"')
        self.assertNotIn("virtual_ride", edit.context["form"].fields)
        self.organizer.api_token = uuid.uuid4()
        self.organizer.save(update_fields=["api_token"])
        other = self.race(kind=GroupRide.Kind.RIDE)
        patched = self.client.patch(
            f"/api/v1/competitions/{event.pk}",
            data=json.dumps({"title": {"ru": "Renamed"}, "virtual_ride": other.pk}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.organizer.api_token}",
        )
        self.assertEqual(patched.status_code, 200, patched.content)
        event.refresh_from_db()
        self.assertEqual((event.title_ru, event.virtual_ride), ("Renamed", ride.pk))

    def test_the_api_names_the_ride_an_event_is_ridden_in(self):
        ride = self.race()
        self.draft(virtual_ride=str(ride.pk), registration="1")
        self.submit(self.form_page().context["draft_key"])
        event = Competition.objects.get(title_ru="Virtual race")
        answer = self.client.get(f"/api/v1/competitions/{event.pk}").json()
        self.assertTrue(
            answer["virtual_ride_url"].endswith(f"/virtual-ride/?group={ride.pk}"), answer["virtual_ride_url"]
        )

    def test_the_route_s_track_is_attached_unless_the_member_chose_a_file(self):
        self.draft(track_name="oldtown", track_gpx=GPX)
        page = self.form_page()
        self.assertContains(page, 'id="route-draft-track"')
        with mock.patch.object(Competition, "save", autospec=True, side_effect=Competition.save) as saved:
            self.submit(page.context["draft_key"])
        self.assertEqual(saved.call_count, 1)  # the track goes on without the event saved, logged and pinged again
        event = Competition.objects.get(title_ru="Virtual race")
        self.assertTrue(event.file_route.name.endswith("oldtown.gpx"), event.file_route.name)
        self.assertEqual(event.file_route.read().decode(), GPX)

    def test_the_ride_s_picture_shows_on_the_form_and_is_the_event_s_unless_the_member_chose_one(self):
        self.draft(**PICTURE)
        page = self.form_page()
        self.assertContains(page, 'id="ride-picture"')
        shown = self.client.get(page.context["draft_picture"])
        self.assertEqual(shown["Content-Type"], "image/jpeg")
        self.assertEqual(Image.open(io.BytesIO(shown.content)).size, (ride_picture.WIDTH, ride_picture.HEIGHT))
        self.submit(page.context["draft_key"])
        event = Competition.objects.get(title_ru="Virtual race")
        self.assertEqual(Image.open(event.preview_image).size, (ride_picture.WIDTH, ride_picture.HEIGHT))
        # a picture of the member's own is the event's
        self.draft(**PICTURE)
        own = io.BytesIO()
        Image.new("RGB", (400, 300), "navy").save(own, "PNG")
        payload = {
            "title_ru": "Own picture",
            "date_start": "2026-12-02",
            "location": str(self.start.pk),
            "draft_key": self.form_page().context["draft_key"],
            "preview_image": SimpleUploadedFile("own.png", own.getvalue(), content_type="image/png"),
        }
        self.client.post(reverse("calendar_submit"), payload)
        self.assertEqual(Image.open(Competition.objects.get(title_ru="Own picture").preview_image).size, (400, 300))

    def test_a_skin_without_its_heading_s_italic_gives_no_picture_rather_than_failing(self):
        # the day and time are drawn in the heading's italic: without it the page failed, the event being saved too
        real = ride_picture._faces
        no_italic = mock.patch.object(
            ride_picture,
            "_faces",
            side_effect=lambda skin, role, style: () if style == ride_picture.ITALIC else real(skin, role, style),
        )
        with no_italic:
            self.assertIsNone(ride_picture.draw("oldtown", "Sat 28 Nov, 18:00", "Virtual race", "15 km"))
        self.assertIsNotNone(ride_picture.draw("oldtown", "Sat 28 Nov, 18:00", "Virtual race", "15 km"))

    def test_a_route_without_a_view_has_no_picture_and_a_draft_s_picture_is_its_own_member_s(self):
        self.draft(**{**PICTURE, "picture_route": "no-such-route"})
        self.assertEqual(self.form_page().context["draft_picture"], "")
        self.draft(**PICTURE)
        address = self.form_page().context["draft_picture"]
        self.assertEqual(self.client.get(reverse("calendar_draft_picture", args=["another-key"])).status_code, 404)
        someone = User.objects.create_user(
            username="someone", email="s@example.com", password="Pass1234!", role=User.Role.PARTICIPANT
        )
        self.client.force_login(someone)  # a session without that draft
        self.assertEqual(self.client.get(address).status_code, 404)

    def test_a_track_file_of_the_member_s_own_is_the_event_s(self):
        self.draft(track_name="oldtown", track_gpx=GPX)
        payload = {
            "title_ru": "Own track",
            "date_start": "2026-12-02",
            "location": str(self.start.pk),
            "draft_key": self.form_page().context["draft_key"],
            "file_route": SimpleUploadedFile("mine.gpx", GPX.encode(), content_type="application/gpx+xml"),
        }
        self.client.post(reverse("calendar_submit"), payload)
        self.assertTrue(Competition.objects.get(title_ru="Own track").file_route.name.endswith("mine.gpx"))

    def test_a_participant_s_race_and_a_race_started_or_cancelled_meanwhile_are_not_held(self):
        rider = User.objects.create_user(
            username="rider2", email="rider2@example.com", password="Pass1234!", role=User.Role.PARTICIPANT
        )
        self.client.force_login(rider)
        theirs = self.race(host=rider)
        self.draft(virtual_ride=str(theirs.pk), registration="1")
        self.submit(self.form_page().context["draft_key"], title="A participant's")
        theirs.refresh_from_db()
        self.assertIsNone(theirs.competition)  # only an organizer's form registers riders
        self.client.force_login(self.organizer)
        started, cancelled = self.race(), self.race()
        for race, title in ((started, "Started"), (cancelled, "Cancelled")):
            self.draft(virtual_ride=str(race.pk), registration="1")
            key = self.form_page().context["draft_key"]
            if race is started:
                GroupRide.objects.filter(pk=race.pk).update(start_at=timezone.now() - timedelta(minutes=1))
            else:
                GroupRide.objects.filter(pk=race.pk).update(cancelled=True)
            self.submit(key, title=title, registers=True)
            race.refresh_from_db()
            self.assertIsNone(race.competition, title)
        self.assertIsNone(Competition.objects.get(title_ru="Cancelled").virtual_ride)  # nor linked

    def test_what_holds_no_track_is_not_attached(self):
        self.draft(track_name="oldtown", track_gpx="<gpx>nothing to draw</gpx>")
        self.assertFalse(self.form_page().context["draft_track"])

    def test_the_race_is_held_by_the_event_made_from_its_draft(self):
        race = self.race()
        self.draft(virtual_ride=str(race.pk), registration="1")
        self.submit(self.form_page().context["draft_key"], registers=True)
        race.refresh_from_db()
        event = Competition.objects.get(title_ru="Virtual race")
        self.assertTrue(event.registration_enabled)
        self.assertEqual(race.competition, event)

    def test_who_gathered_in_a_race_before_its_event_held_it_joins_again_once_registered(self):
        race = self.race()
        GroupRideMember.objects.create(group=race, user=self.organizer)  # the host, in it since they gathered it
        self.draft(virtual_ride=str(race.pk), registration="1")
        self.submit(self.form_page().context["draft_key"], registers=True)
        race.refresh_from_db()
        self.assertIsNotNone(race.competition)
        # without a registration and a bib they would ride it untimed
        self.assertFalse(race.memberships.exists())
        self.assertEqual(race.last_start_at, race.start_at)

    def test_an_organizer_is_told_when_their_race_was_not_held_and_another_tab_s_draft_stays(self):
        race = self.race()
        self.draft(virtual_ride=str(race.pk), registration="1")
        key = self.form_page().context["draft_key"]
        # an event made by hand meanwhile, in another tab: the draft is still there for its own form
        self.submit("", title="By hand")
        self.assertEqual(self.client.session["event_draft"]["key"], key)
        answer = self.submit(key, registers=False)
        told = [str(m) for m in get_messages(answer.wsgi_request)]
        self.assertIn(
            gettext(
                "The race is not held by this event: only an event with registration on the site holds a "
                "race, before it starts."
            ),
            told,
        )
        self.assertNotIn("event_draft", self.client.session)

    def test_the_warning_names_why_the_event_does_not_hold_the_race(self):
        # it said "only an event with registration" to an organizer whose event was invite-only, or awaited review
        told = {}
        cases = (
            ("invite-only", {"invite_only": "on"}),
            ("on a place under review", {"under_review": True}),
            ("over", {"date_start": "2020-01-02"}),  # it was told to register on the site, which it did
        )
        for case, extra in cases:
            race = self.race()
            self.draft(virtual_ride=str(race.pk), registration="1")
            key = self.form_page().context["draft_key"]
            if extra.pop("under_review", False):  # the city above the place awaits review: so does the event
                LocationProposal.objects.create(location=self.city, submitted_by=self.organizer)
            payload = {"title_ru": case, "date_start": "2026-12-02", "location": str(self.start.pk), "draft_key": key}
            answer = self.client.post(reverse("calendar_submit"), {**payload, "registration_enabled": "on", **extra})
            told[case] = [str(m) for m in get_messages(answer.wsgi_request)]
            race.delete()
        self.assertEqual(
            told,
            {
                "invite-only": [
                    gettext(
                        "The race is not held by this event: only a public event, neither hidden nor by invitation, "
                        "holds a race."
                    )
                ],
                "on a place under review": [
                    gettext(
                        "The race is not held by this event: it awaits review, and only a published event holds a race."
                    )
                ],
                "over": [
                    gettext(
                        "The race is not held by this event: the event is over, and only one still to come holds a "
                        "race."
                    )
                ],
            },
        )

    def test_an_event_that_registers_nobody_or_is_over_holds_no_race(self):
        # a race held by them could be joined by no one: joining asks for a registration
        for title, registers, day in (("No registration", False, "2026-12-02"), ("Over", True, "2020-01-02")):
            race = self.race()
            self.draft(virtual_ride=str(race.pk), registration="1")
            self.submit(self.form_page().context["draft_key"], title=title, registers=registers, day=day)
            race.refresh_from_db()
            self.assertTrue(Competition.objects.filter(title_ru=title).exists(), title)
            self.assertIsNone(race.competition, title)

    def test_a_form_opened_otherwise_takes_nothing_of_a_draft_left_over(self):
        race = self.race()
        self.draft(virtual_ride=str(race.pk), track_name="oldtown", track_gpx=GPX)
        self.submit("")  # the form opened by hand later sends no key
        race.refresh_from_db()
        self.assertIsNone(race.competition)
        event = Competition.objects.get(title_ru="Virtual race")
        self.assertFalse(event.file_route)
        self.assertIsNone(event.virtual_ride)

    def test_someone_else_s_race_is_neither_held_nor_linked_and_a_ride_is_only_linked(self):
        other = User.objects.create_user(
            username="other", email="other@example.com", password="Pass1234!", role=User.Role.ORGANIZER
        )
        theirs, ride = self.race(host=other), self.race(kind=GroupRide.Kind.RIDE)
        for race in (theirs, ride):
            self.draft(virtual_ride=str(race.pk))
            self.submit(self.form_page().context["draft_key"], title=f"Virtual race {race.pk}")
            race.refresh_from_db()
            self.assertIsNone(race.competition)
        self.assertIsNone(Competition.objects.get(title_ru=f"Virtual race {theirs.pk}").virtual_ride)
        self.assertEqual(Competition.objects.get(title_ru=f"Virtual race {ride.pk}").virtual_ride, ride.pk)
