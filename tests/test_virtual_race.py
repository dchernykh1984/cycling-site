"""A virtual race with protocols (specs/495-virtual-race): made by the event's organizer, joined by its registered
riders with bibs, its start list, groups' starts and crossings written into the event's timing streams for
FinishProtocolGenerator -- only while the event keeps its upload token."""

import re
import uuid
from datetime import timedelta

from django.test import Client, TestCase
from django.utils import timezone

from accounts.models import User
from event_photos.bindings import parse_line
from event_photos.models import IssuedBib
from protocols.models import FinishTimesUpload, GroupTimesUpload, RemotePointUpload, StartListUpload
from registrations.tests import make_category, make_open_competition, make_registration, make_user
from trainer import race
from trainer.models import GroupRide, GroupRideMember

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

    def test_the_organizer_s_list_of_events_holds_their_own_to_come(self):
        mine = self.client_of(self.organizer).get(f"{API}/events").json()
        self.assertEqual([e["id"] for e in mine], [self.event.pk])
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

    def test_a_rider_without_a_registration_is_sent_to_register_first(self):
        group = self.make().json()["id"]
        refused = self.join(_member("dana"), group)
        self.assertEqual(refused.status_code, 403)
        self.assertIn(self.event.get_absolute_url(), refused.json()["detail"])
        rejected = self.rider("emil", self.elite, is_rejected=True)
        self.assertEqual(self.join(rejected, group).status_code, 403)

    def test_a_bib_the_event_gave_the_registration_is_kept(self):
        group = self.make().json()["id"]
        anna = self.rider("anna", self.women)
        registration = race.registration_of(anna, self.event)
        IssuedBib.objects.create(competition=self.event, registration=registration, bib="77", device_id="spm")
        self.assertEqual(self.join(anna, group).json()["me"]["bib"], "77")

    def test_a_route_that_is_not_a_loop_is_ridden_once_whatever_the_category_s_laps(self):
        group = self.make(route="kyrbaltabay-tuganbay", loop=False).json()["id"]
        anna = self.rider("anna", self.elite)
        self.assertEqual(self.join(anna, group).json()["me"]["laps"], 1)
        self.assertEqual(self.stream(StartListUpload)[0].split("#")[3], "1")

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
