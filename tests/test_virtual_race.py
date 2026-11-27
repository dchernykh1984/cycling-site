"""A virtual race with protocols (specs/495-virtual-race): made by the event's organizer, joined by its registered
riders with bibs, its start list, groups' starts and crossings written into the event's timing streams for
FinishProtocolGenerator -- only while the event keeps its upload token."""

import re
import threading
import uuid
from datetime import timedelta
from unittest import mock

from django.db import connections
from django.db.models import F
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone, translation

from accounts.models import User
from event_photos.bindings import parse_line
from event_photos.models import IssuedBib
from protocols.models import FinishTimesUpload, GroupTimesUpload, RemotePointUpload, StartListUpload
from registrations.tests import make_category, make_open_competition, make_registration, make_user
from tests.test_virtual_ride_api import _ride as _saved_ride
from trainer import race
from trainer.models import GroupRide, GroupRideMember, VirtualRide

API = "/api/v1/virtual-ride"
#: The chronometer's moment, as FinishProtocolGenerator parses it: days since 1970, then the time of day
CLOCK = re.compile(r"\d+ \d{1,2}:\d{1,2}:\d{1,2}\.\d{3}")


def _member(username, role=User.Role.PARTICIPANT):
    return make_user(username, role=role, first_name=username.title(), last_name="Rider")


class RaceTestCase(TestCase):
    def setUp(self):
        self.organizer = _member("organizer", User.Role.ORGANIZER)
        self.event = make_open_competition(submitted_by=self.organizer)
        self.elite = make_category(self.event, "Elite", laps=3, bib_from=11, bib_to=12, order=0)
        self.women = make_category(self.event, "Women", laps=2, bib_from=51, bib_to=60, order=1)

    def client_of(self, user) -> Client:
        client = Client()
        client.force_login(user)
        return client

    def make(self, **over):
        payload = {
            "route": "granfondo",
            "route_name": "Granfondo 2026",
            "start_in_s": 600,
            "competition_id": self.event.pk,
        }
        payload.update(over)
        return self.client_of(self.organizer).post(f"{API}/groups", payload, content_type="application/json")

    def rider(self, username, category, **registration):
        user = _member(username)
        make_registration(
            self.event, user=user, category=category, first_name=username.title(), last_name="Rider", **registration
        )
        return user

    def join(self, user, group_id):
        return self.client_of(user).post(f"{API}/groups/{group_id}/join")

    def stream(self, model, **key):
        row = model.objects.filter(
            competition=self.event, device_id=f"virtual-race-{GroupRide.objects.get().pk}", **key
        ).first()
        return row.items if row else []


class MakingARaceTests(RaceTestCase):
    def test_the_event_s_organizer_makes_a_race_for_it_with_its_settings(self):
        made = self.make(mode="itt", itt_interval_s=45, group_gap_s=0, draft_between_groups=False)
        self.assertEqual(made.status_code, 201, made.content)
        body = made.json()
        self.assertEqual(body["event"]["id"], self.event.pk)
        # its title in every language, for the page to name it in its own
        self.assertEqual(set(body["event"]["title"]), {"ru", "kk", "en"})
        self.assertEqual((body["mode"], body["itt_interval_s"], body["draft_between_groups"]), ("itt", 45, False))
        # the organizer is not registered: they host the race without riding it
        self.assertEqual((body["is_host"], body["is_member"], body["members"]), (True, False, []))

    def test_nobody_else_ties_a_race_to_the_event_and_an_admin_ties_one_to_any(self):
        other = _member("other", User.Role.ORGANIZER)
        refused = self.client_of(other).post(
            f"{API}/groups",
            {"route": "granfondo", "start_in_s": 600, "competition_id": self.event.pk},
            content_type="application/json",
        )
        self.assertEqual(refused.status_code, 403)
        admin = _member("admin", User.Role.ADMIN)
        made = self.client_of(admin).post(
            f"{API}/groups",
            {"route": "granfondo", "start_in_s": 600, "competition_id": self.event.pk},
            content_type="application/json",
        )
        self.assertEqual(made.status_code, 201)

    def test_a_finished_or_unapproved_event_takes_no_race(self):
        self.event.date_start = self.event.date_end = timezone.localdate() - timedelta(days=1)
        self.event.save(update_fields=["date_start", "date_end"])
        self.assertEqual(self.make().status_code, 403)

    def test_a_hidden_or_invite_only_event_takes_no_race_and_one_closed_later_is_not_named(self):
        for closed in ("is_hidden", "invite_only"):
            setattr(self.event, closed, True)
            self.event.save(update_fields=[closed])
            self.assertEqual(self.make().status_code, 403, closed)
            self.assertEqual(self.client_of(self.organizer).get(f"{API}/events").json(), [], closed)
            setattr(self.event, closed, False)
            self.event.save(update_fields=[closed])
        group = self.make().json()["id"]
        self.event.invite_only = True
        self.event.save(update_fields=["invite_only"])
        # every member's lobby lists the race: an event that is no longer public is not named there
        self.assertIsNone(self.client_of(_member("someone")).get(f"{API}/groups/{group}").json()["event"])

    def test_the_organizer_s_list_of_events_holds_their_own_to_come(self):
        mine = self.client_of(self.organizer).get(f"{API}/events").json()
        self.assertEqual([(e["id"], e["registered"]) for e in mine], [(self.event.pk, False)])
        make_registration(
            self.event, user=self.organizer, category=self.elite, first_name="Organizer", last_name="Rider"
        )
        mine = self.client_of(self.organizer).get(f"{API}/events").json()
        self.assertEqual([(e["id"], e["registered"]) for e in mine], [(self.event.pk, True)])
        self.assertEqual(self.client_of(_member("someone")).get(f"{API}/events").json(), [])


class JoiningTests(RaceTestCase):
    def test_a_registered_rider_joins_with_the_first_free_bib_of_their_category(self):
        group = self.make().json()["id"]
        anna, boris = self.rider("anna", self.elite), self.rider("boris", self.elite)
        self.assertEqual(
            self.join(anna, group).json()["me"], {"bib": "11", "group": "Elite", "laps": 3, "start_offset_s": 0}
        )
        self.assertEqual(self.join(boris, group).json()["me"]["bib"], "12")
        # the range is used up: the next rider is told so
        self.assertEqual(self.join(self.rider("carl", self.elite), group).status_code, 409)

    def test_a_rider_who_leaves_and_joins_again_keeps_their_bib(self):
        group = self.make().json()["id"]
        anna, boris = self.rider("anna", self.elite), self.rider("boris", self.elite)
        self.assertEqual(self.join(anna, group).json()["me"]["bib"], "11")
        self.client_of(anna).post(f"{API}/groups/{group}/leave")
        # the bib left behind is not given to the next rider, and comes back with its rider
        self.assertEqual(self.join(boris, group).json()["me"]["bib"], "12")
        self.assertEqual(self.join(anna, group).json()["me"]["bib"], "11")

    def test_a_rider_without_a_registration_is_sent_to_register_first(self):
        group = self.make().json()["id"]
        refused = self.join(_member("dana"), group)
        self.assertEqual(refused.status_code, 403)
        self.assertIn(self.event.get_absolute_url(), refused.json()["detail"])
        rejected = self.rider("emil", self.elite, is_rejected=True)
        self.assertEqual(self.join(rejected, group).status_code, 403)

    def test_a_race_card_says_whether_the_member_is_registered_and_where_to_register_or_see_who_is(self):
        """ "Join" did nothing for a member the event did not have: the card now says whether it has them, and where
        to register or to see who is registered -- on the race, in the lobby's list and in its presence alike."""
        group = self.make().json()["id"]
        register = reverse("registrations:register", kwargs={"pk": self.event.pk})
        participants = reverse("registrations:participant_list", kwargs={"pk": self.event.pk})
        riders = {
            "registered": (self.rider("anna", self.elite), True),
            "rejected": (self.rider("emil", self.elite, is_rejected=True), False),
            "not": (_member("dana"), False),
        }
        for who, (user, registered) in riders.items():
            client = self.client_of(user)
            lobby = client.post(f"{API}/presence", {"status": "lobby"}, content_type="application/json").json()
            cards = [
                client.get(f"{API}/groups/{group}").json(),
                next(g for g in client.get(f"{API}/groups").json() if g["id"] == group),
                next(g for g in lobby["groups"] if g["id"] == group),
            ]
            for card in cards:
                event = card["event"]
                self.assertEqual(
                    (event["registered"], event["register_url"], event["participants_url"]),
                    (registered, register, participants),
                    who,
                )

    def test_a_bib_the_event_gave_the_registration_is_kept(self):
        group = self.make().json()["id"]
        anna = self.rider("anna", self.women)
        registration = race.registration_of(anna, self.event)
        IssuedBib.objects.create(competition=self.event, registration=registration, bib="77", device_id="spm")
        self.assertEqual(self.join(anna, group).json()["me"]["bib"], "77")

    def test_a_route_that_is_not_a_loop_is_ridden_once_whatever_the_category_s_laps(self):
        group = self.make(route="medeu", loop=False).json()["id"]
        anna = self.rider("anna", self.elite)
        self.assertEqual(self.join(anna, group).json()["me"]["laps"], 1)
        self.assertEqual(self.stream(StartListUpload)[0].split("#")[3], "1")

    def test_a_race_with_protocols_stays_its_maker_s_when_they_leave_it(self):
        make_registration(self.event, user=self.organizer, category=self.women)
        group = self.make().json()["id"]
        boris = self.rider("boris", self.elite)
        self.join(boris, group)
        left = self.client_of(self.organizer).post(f"{API}/groups/{group}/leave").json()
        # neither cancelled nor handed to the rider who joined next: the event's race is its organizer's
        self.assertEqual((left["cancelled"], left["is_host"], left["is_member"]), (False, True, False))
        alone = GroupRide.objects.get(pk=group)
        alone.memberships.all().delete()
        self.client_of(self.organizer).post(f"{API}/groups/{group}/leave")
        self.assertFalse(GroupRide.objects.get(pk=group).cancelled)

    def test_a_registered_organizer_rides_the_race_they_made(self):
        make_registration(self.event, user=self.organizer, category=self.women)
        body = self.make().json()
        self.assertEqual(body["is_member"], True)
        self.assertEqual(body["me"]["bib"], "51")


class TimingTests(RaceTestCase):
    def test_the_start_list_and_the_groups_starts_are_written_as_the_tools_read_them(self):
        group = self.make(group_gap_s=120).json()["id"]
        anna, boris = self.rider("anna", self.elite, city="Almaty"), self.rider("boris", self.women)
        self.join(anna, group)
        self.join(boris, group)
        lines = self.stream(StartListUpload)
        self.assertEqual(len(lines), 2)
        first = lines[0].split("#")
        self.assertEqual(first[:5], ["11", "Rider Anna", "Elite", "3", "1"])
        self.assertEqual((first[5], first[7], first[9]), ("1990", "Almaty", ""))
        registration = race.registration_of(anna, self.event)
        line, warning = parse_line(lines[0], max_stages=10)
        self.assertEqual((line.bibs, line.refs, warning), (("11",), (registration.pk,), ""))
        # the bindings the start list makes: the bib is the registration's on the rest of the site
        self.assertTrue(IssuedBib.objects.filter(registration=registration, bib="11").exists())
        starts = dict(item.split("#")[:2] for item in self.stream(GroupTimesUpload))
        self.assertEqual(set(starts), {"Elite", "Women"})
        self.assertTrue(all(CLOCK.fullmatch(t) for t in starts.values()), starts)
        # the second category two minutes after the first
        seconds = {
            g: sum(int(x) * k for x, k in zip(t.split(" ")[1].split(".")[0].split(":"), (3600, 60, 1), strict=True))
            for g, t in starts.items()
        }
        self.assertEqual((seconds["Women"] - seconds["Elite"]) % 86400, 120)

    def test_a_time_trial_starts_each_rider_an_interval_after_the_one_before(self):
        group = self.make(mode="itt", itt_interval_s=30).json()["id"]
        for name, category in (("anna", self.elite), ("boris", self.elite), ("vera", self.women)):
            self.join(self.rider(name, category), group)
        delays = [line.split("#")[9] for line in self.stream(StartListUpload)]
        self.assertEqual(delays, ["0:00:00", "0:00:30", "0:01:00"])
        mine = self.client_of(GroupRideMember.objects.get(bib="51").user).get(f"{API}/groups/{group}").json()["me"]
        self.assertEqual(mine["start_offset_s"], 60)

    def test_the_lobby_lists_a_time_trial_until_moments_after_its_last_rider_s_start(self):
        group = self.make(mode="itt", itt_interval_s=60).json()["id"]
        riders = [self.rider(f"rider{k}", self.women) for k in range(7)]
        for user in riders:
            self.join(user, group)
        # six minutes on: the race's start is long past, the last of its seven riders starts in a minute
        moved = timezone.now() - GroupRide.objects.get(pk=group).start_at + timedelta(minutes=6)
        GroupRide.objects.filter(pk=group).update(
            start_at=F("start_at") - moved, last_start_at=F("last_start_at") - moved
        )
        lobby = self.client_of(riders[-1]).post(
            f"{API}/presence", {"status": "lobby", "route": "granfondo"}, content_type="application/json"
        )
        mine = next(g for g in lobby.json()["groups"] if g["id"] == group)
        self.assertEqual(mine["me"]["start_offset_s"], 360)

    def test_places_are_counted_within_each_category_and_the_results_name_it(self):
        group = self.make().json()["id"]
        anna, boris, vera = (
            self.rider("anna", self.elite),
            self.rider("boris", self.women),
            self.rider("vera", self.women),
        )
        for user in (anna, boris, vera):
            self.join(user, group)
        for user, seconds in ((anna, 3000.0), (boris, 2000.0), (vera, 2500.0)):
            saved = self.client_of(user).post(
                f"{API}/rides", _saved_ride(group_id=group, duration_s=seconds), content_type="application/json"
            )
            self.assertEqual(saved.status_code, 201, saved.content)
        # the elite rider rides three laps, the women two: each ranked among their own category's riders
        places = {r.user_id: (r.place, r.field_size) for r in VirtualRide.objects.all()}
        self.assertEqual(places, {anna.pk: (1, 1), boris.pk: (1, 2), vera.pk: (2, 2)})
        results = self.client_of(anna).get(f"{API}/groups/{group}/results").json()["finished"]
        self.assertEqual(
            {r["user_id"]: r["group"] for r in results}, {anna.pk: "Elite", boris.pk: "Women", vera.pk: "Women"}
        )

    def _ride(self, user, group, crossings):
        return self.client_of(user).post(
            f"{API}/presence",
            {"status": "ride", "route": "granfondo", "group_id": group, "crossings": crossings},
            content_type="application/json",
        )

    def _start_now(self, group):
        GroupRide.objects.filter(pk=group).update(start_at=timezone.now() - timedelta(minutes=30))

    def test_crossings_are_written_once_the_last_lap_as_the_finish(self):
        group = self.make().json()["id"]
        anna = self.rider("anna", self.women)
        self.join(anna, group)
        self._start_now(group)
        now = int(timezone.now().timestamp() * 1000)
        lap = {"point": 0, "at_ms": now - 600_000}
        turn = {"point": 1, "at_ms": now - 900_000}
        finish = {"point": 0, "at_ms": now - 1000, "last": True}
        self.assertEqual(self._ride(anna, group, [turn, lap]).status_code, 200)
        self._ride(anna, group, [turn, lap, finish])  # a retry with one more: each written once
        finish_lines = self.stream(FinishTimesUpload)
        self.assertEqual([line.split("#")[2] for line in finish_lines], ["nextLap", "finish"])
        self.assertTrue(all(line.startswith("51#") and CLOCK.fullmatch(line.split("#")[1]) for line in finish_lines))
        self.assertEqual(len(self.stream(RemotePointUpload, point_number=1)), 1)

    def test_a_rider_whose_registration_is_gone_leaves_the_start_list_and_the_race_goes_on(self):
        group = self.make().json()["id"]
        anna, boris = self.rider("anna", self.elite), self.rider("boris", self.women)
        self.join(anna, group)
        race.registration_of(anna, self.event).delete()
        self.assertEqual(self.join(boris, group).status_code, 200)
        self.assertEqual([line.split("#")[0] for line in self.stream(StartListUpload)], ["51"])
        # nor are their crossings written, which FinishProtocolGenerator could not match with anyone
        self._start_now(group)
        now = int(timezone.now().timestamp() * 1000)
        self._ride(anna, group, [{"point": 0, "at_ms": now - 1000}])
        self.assertEqual(self.stream(FinishTimesUpload), [])

    def test_a_rider_s_crossings_of_a_point_stop_at_their_laps(self):
        group = self.make().json()["id"]
        anna = self.rider("anna", self.women)  # two laps
        self.join(anna, group)
        self._start_now(group)
        now = int(timezone.now().timestamp() * 1000)
        self._ride(anna, group, [{"point": 0, "at_ms": now - k * 60_000} for k in range(1, 6)])
        self._ride(anna, group, [{"point": 1, "at_ms": now - k * 60_000} for k in range(1, 6)])
        self.assertEqual(len(self.stream(FinishTimesUpload)), 2)
        self.assertEqual(len(self.stream(RemotePointUpload, point_number=1)), 2)

    def test_a_crossing_before_the_rider_s_start_or_ahead_of_now_is_not_written(self):
        group = self.make().json()["id"]
        anna = self.rider("anna", self.women)
        self.join(anna, group)
        self._start_now(group)
        now = int(timezone.now().timestamp() * 1000)
        self._ride(anna, group, [{"point": 0, "at_ms": now - 3_600_000}, {"point": 0, "at_ms": now + 60_000}])
        self.assertEqual(self.stream(FinishTimesUpload), [])

    def test_without_the_event_s_token_the_race_writes_nothing_and_never_makes_one(self):
        group = self.make().json()["id"]
        anna = self.rider("anna", self.women)
        self.event.upload_token = None
        self.event.save(update_fields=["upload_token"])
        self.join(anna, group)
        self._start_now(group)
        self._ride(anna, group, [{"point": 0, "at_ms": int(timezone.now().timestamp() * 1000) - 1000}])
        self.assertEqual((self.stream(StartListUpload), self.stream(FinishTimesUpload)), ([], []))
        self.event.refresh_from_db()
        self.assertIsNone(self.event.upload_token)
        # a regenerated token: the race writes again, for the generator to read with the new one
        self.event.upload_token = uuid.uuid4()
        self.event.save(update_fields=["upload_token"])
        self._ride(anna, group, [{"point": 0, "at_ms": int(timezone.now().timestamp() * 1000) - 1000}])
        self.assertEqual(len(self.stream(FinishTimesUpload)), 1)

    def test_the_riders_of_a_race_come_back_with_their_bibs_and_drag_areas(self):
        group = self.make().json()["id"]
        anna, boris = self.rider("anna", self.elite), self.rider("boris", self.women)
        self.join(anna, group)
        self.join(boris, group)
        self.client_of(boris).post(
            f"{API}/presence",
            {"status": "ride", "route": "granfondo", "group_id": group, "cda": 0.41},
            content_type="application/json",
        )
        seen = self._ride(anna, group, []).json()["riders"]
        self.assertEqual([(r["bib"], r["group"], r["cda"]) for r in seen], [("51", "Women", 0.41)])


class RefusalsTests(TestCase):
    def test_a_race_s_refusals_are_in_russian_and_kazakh_too(self):
        refusals = (
            "Register for the event first: %(link)s",
            "Your category has no free bib left",
            "Only the event's organizer can make a race for it",
        )
        for language in ("ru", "kk"):
            for text in refusals:
                with self.subTest(language=language, text=text), translation.override(language):
                    self.assertNotEqual(translation.gettext(text), text)


class JoiningAtOnceTests(TransactionTestCase):
    def test_two_riders_joining_two_races_of_one_event_at_once_get_different_bibs(self):
        organizer = _member("organizer", User.Role.ORGANIZER)
        event = make_open_competition(submitted_by=organizer)
        category = make_category(event, "Open", laps=1, bib_from=11, bib_to=20, order=0)
        anna, boris = _member("anna"), _member("boris")
        for user in (anna, boris):
            make_registration(event, user=user, category=category, first_name=user.first_name, last_name="Rider")
        maker = Client()
        maker.force_login(organizer)
        races = [
            maker.post(f"{API}/groups", {"route": "center", "competition_id": event.pk, **when}, "application/json")
            for when in ({"start_in_s": 600}, {"start_at": (timezone.now() + timedelta(hours=3)).isoformat()})
        ]
        held, go = threading.Event(), threading.Event()
        assign = race.assign_bib

        def assign_then_hold(member):
            bib = assign(member)
            if not held.is_set():
                held.set()
                go.wait(timeout=10)  # the first rider's join still open with the bib it chose
            return bib

        def join(user, group_id):
            try:
                rider = Client()
                rider.force_login(user)
                rider.post(f"{API}/groups/{group_id}/join")
            finally:
                connections.close_all()

        with mock.patch.object(race, "assign_bib", side_effect=assign_then_hold):
            first = threading.Thread(target=join, args=(anna, races[0].json()["id"]))
            first.start()
            self.assertTrue(held.wait(timeout=10))
            second = threading.Thread(target=join, args=(boris, races[1].json()["id"]))
            second.start()
            second.join(timeout=1)
            go.set()
            first.join(timeout=10)
            second.join(timeout=10)
        self.assertEqual(sorted(GroupRideMember.objects.values_list("bib", flat=True)), ["11", "12"])


class GatheringARideOrARaceTests(TestCase):
    """The page gathers what its mode is set to: a free ride a ride together, a race a race -- a time trial without an
    event starting its riders in the order they joined."""

    def setUp(self):
        self.host = _member("host")

    def gather(self, user, **over):
        client = Client()
        client.force_login(user)
        payload = {"route": "granfondo", "route_name": "Granfondo 2026", "start_in_s": 600, **over}
        return client.post(f"{API}/groups", payload, content_type="application/json")

    def seen_by(self, user, path):
        client = Client()
        client.force_login(user)
        return client.get(f"{API}{path}").json()

    def test_a_ride_together_is_gathered_and_listed_as_a_ride(self):
        made = self.gather(self.host, kind="ride")
        self.assertEqual(made.status_code, 201, made.content)
        self.assertEqual(made.json()["kind"], "ride")
        self.assertEqual([g["kind"] for g in self.seen_by(_member("guest"), "/groups")], ["ride"])
        # a race is a race, as it was before rides were told apart
        self.assertEqual(self.gather(_member("racer")).json()["kind"], "race")

    def test_a_ride_together_has_neither_a_time_trial_nor_an_event(self):
        self.assertEqual(self.gather(self.host, kind="ride", mode="itt").status_code, 422)
        event = make_open_competition(submitted_by=self.host)
        self.assertEqual(self.gather(self.host, kind="ride", competition_id=event.pk).status_code, 422)
        self.assertFalse(GroupRide.objects.exists())

    def test_a_time_trial_without_an_event_starts_its_riders_in_the_order_they_joined(self):
        group = self.gather(self.host, mode="itt", itt_interval_s=30).json()["id"]
        riders = [_member("anna"), _member("boris")]
        for user in riders:
            client = Client()
            client.force_login(user)
            self.assertEqual(client.post(f"{API}/groups/{group}/join").status_code, 200)
        offsets = [self.seen_by(user, f"/groups/{group}")["me"]["start_offset_s"] for user in (self.host, *riders)]
        self.assertEqual(offsets, [0, 30, 60])
        # the lobby keeps it until moments after its last rider's own start
        made = GroupRide.objects.get(pk=group)
        self.assertEqual(made.last_start_at, made.start_at + timedelta(seconds=60))
        # a race without an event, not a time trial, starts everyone at once as before
        self.assertIsNone(self.gather(_member("vera")).json()["me"])
