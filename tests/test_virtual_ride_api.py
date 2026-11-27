"""Virtual ride on the site: saved rides and records in the profile, group races, riding together."""

import json
import threading
import uuid
from datetime import timedelta
from unittest import mock

from django.db import connection, connections
from django.test import Client, TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext, ngettext
from django.utils.translation import override as translation_override

from accounts.models import User
from trainer import records
from trainer.live import ONLINE_SECONDS
from trainer.models import GroupRide, GroupRideMember, LiveRider, TrainerSettings, VirtualRide

API = "/api/v1/virtual-ride"


def _user(username, **kwargs):
    kwargs.setdefault("role", User.Role.PARTICIPANT)
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="Pass1234!", first_name=username.title(), **kwargs
    )
    user.api_token = uuid.uuid4()
    user.save(update_fields=["api_token"])
    return user


def _ride(**overrides):
    ride = {
        "route": "center",
        "route_name": "Center loop",
        "kind": "race",
        "duration_s": 1500.0,
        "distance_m": 10600.0,
        "elevation_gain_m": 125,
        "avg_speed_kmh": 25.4,
        "max_speed_kmh": 41.2,
        "avg_power_w": 190,
        "avg_cadence_rpm": 86,
        "power_source": "measured",
        "peak_5s_w": 600,
        "peak_1m_w": 380,
        "peak_5m_w": 250,
        "peak_20m_w": 200,
    }
    ride.update(overrides)
    return ride


class MemberClientMixin:
    def member(self, user) -> Client:
        client = Client()
        client.force_login(user)
        return client

    def post(self, client, path, data=None):
        return client.post(f"{API}{path}", data=json.dumps(data or {}), content_type="application/json")


class TrainerSettingsTests(MemberClientMixin, TestCase):
    """The trainer page's settings kept with the member's account, stamped by the site's clock: a page replaces
    the copy kept only if it had that copy, and otherwise is handed the later one."""

    def setUp(self):
        self.user = _user("anna")
        self.anna = self.member(self.user)

    def put(self, client, settings, base):
        return client.put(
            f"{API}/settings", data=json.dumps({"settings": settings, "base": base}), content_type="application/json"
        )

    def test_nothing_kept_yet_is_an_empty_copy_of_no_stamp(self):
        self.assertEqual(self.anna.get(f"{API}/settings").json(), {"settings": {}, "saved_at": 0})

    def test_the_settings_are_kept_as_they_came_under_the_site_s_stamp(self):
        chosen = {"height": 191, "mass": 82, "circ": 2146, "plan": {"steps": [{"f": 2, "r": 6, "min": 5}]}}
        before = int(timezone.now().timestamp() * 1000)
        answer = self.put(self.anna, chosen, 0).json()
        self.assertEqual((answer["settings"], answer["accepted"]), (chosen, True))
        self.assertGreaterEqual(answer["saved_at"], before)
        self.assertEqual(self.anna.get(f"{API}/settings").json(), {"settings": chosen, "saved_at": answer["saved_at"]})

    def test_a_page_that_had_the_copy_kept_replaces_it(self):
        first = self.put(self.anna, {"height": 191}, 0).json()
        second = self.put(self.anna, {"height": 185}, first["saved_at"]).json()
        self.assertTrue(second["accepted"])
        self.assertGreater(second["saved_at"], first["saved_at"])
        self.assertEqual(TrainerSettings.objects.get(user=self.user).data, {"height": 185})

    def test_a_page_that_was_behind_is_handed_the_later_copy(self):
        first = self.put(self.anna, {"height": 191}, 0).json()
        self.put(self.anna, {"height": 185}, first["saved_at"])  # another device, which had the latest
        late = self.put(self.anna, {"height": 170}, first["saved_at"]).json()
        self.assertEqual((late["accepted"], late["settings"]), (False, {"height": 185}))
        self.assertEqual(TrainerSettings.objects.get(user=self.user).data, {"height": 185})

    def test_each_member_has_their_own(self):
        self.put(self.anna, {"height": 191}, 0)
        boris = self.member(_user("boris"))
        self.assertEqual(boris.get(f"{API}/settings").json(), {"settings": {}, "saved_at": 0})

    def test_a_guest_keeps_nothing(self):
        self.assertEqual(self.client.get(f"{API}/settings").status_code, 401)
        self.assertEqual(self.put(self.client, {"height": 191}, 0).status_code, 401)
        self.assertFalse(TrainerSettings.objects.exists())

    def test_what_is_not_settings_is_refused(self):
        for body in ({"settings": [1, 2], "base": 0}, {"settings": {}, "base": -1}, {"base": 0}):
            answer = self.anna.put(f"{API}/settings", data=json.dumps(body), content_type="application/json")
            self.assertEqual(answer.status_code, 422, body)
        self.assertEqual(self.put(self.anna, {"plan": "x" * (64 * 1024)}, 0).status_code, 422)
        self.assertFalse(TrainerSettings.objects.exists())

    def test_deleting_the_account_deletes_them(self):
        self.put(self.anna, {"height": 191}, 0)
        self.user.delete()
        self.assertFalse(TrainerSettings.objects.exists())


class WhoIsRidingTests(MemberClientMixin, TestCase):
    def test_an_anonymous_reader_is_told_to_sign_in(self):
        body = self.client.get(f"{API}/me").json()
        self.assertFalse(body["authenticated"])
        self.assertTrue(body["login_url"])

    def test_a_signed_in_member_is_named_with_their_public_name(self):
        user = _user("anna")
        body = self.member(user).get(f"{API}/me").json()
        self.assertTrue(body["authenticated"])
        self.assertEqual(body["user_id"], user.pk)
        self.assertEqual(body["name"], user.public_display_name)
        # a participant's event form registers no one: their page offers no race's event
        self.assertFalse(body["organizes"])

    def test_an_organizer_is_told_they_may_make_a_race_an_event_with_its_registration(self):
        organizer = _user("olga", role=User.Role.ORGANIZER)
        self.assertTrue(self.member(organizer).get(f"{API}/me").json()["organizes"])

    def test_the_trainer_page_hands_out_the_csrf_cookie_the_framed_page_sends_back(self):
        response = Client().get(reverse("virtual_ride"))
        self.assertIn("csrftoken", response.cookies)


class SavedRidesTests(MemberClientMixin, TestCase):
    def setUp(self):
        self.user = _user("anna")
        self.client_a = self.member(self.user)

    def test_saving_needs_a_member(self):
        response = self.client.post(f"{API}/rides", data=json.dumps(_ride()), content_type="application/json")
        self.assertEqual(response.status_code, 401)

    def test_an_unconfirmed_account_rides_as_a_guest(self):
        # Until the address is confirmed the site's rule holds: no API, no name in the lobby.
        client = self.member(_user("nina", role=User.Role.GUEST))
        self.assertFalse(client.get(f"{API}/me").json()["authenticated"])
        self.assertEqual(self.post(client, "/rides", _ride()).status_code, 401)
        self.assertEqual(self.post(client, "/groups", {"route": "center"}).status_code, 401)
        self.assertEqual(self.post(client, "/presence").status_code, 401)
        self.assertNotContains(client.get(reverse("account_profile")), 'id="virtual-rides"')

    def test_the_first_race_on_a_route_is_its_first_result_and_only_a_faster_one_beats_it(self):
        first = self.post(self.client_a, "/rides", _ride())
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.json()["records"], ["route_first"])
        slower = self.post(self.client_a, "/rides", _ride(duration_s=1600, peak_5s_w=500, max_speed_kmh=30))
        self.assertEqual(slower.json()["records"], [])
        faster = self.post(self.client_a, "/rides", _ride(duration_s=1400, peak_5s_w=650))
        self.assertEqual(faster.json()["records"], ["route_best", "peak_5s_w"])

    def test_a_demo_ride_is_kept_in_the_history_but_never_counts(self):
        self.post(self.client_a, "/rides", _ride())
        demo = self.post(self.client_a, "/rides", _ride(duration_s=900, power_source="demo", peak_5s_w=1500))
        self.assertEqual(demo.json()["records"], [])
        summary = self.client_a.get(f"{API}/records").json()
        self.assertEqual(summary["rides"], 2)
        self.assertEqual(summary["routes"][0]["duration_s"], 1500)
        self.assertEqual(summary["peaks"]["peak_5s_w"], 600)

    def test_a_ride_with_wind_is_kept_with_it_and_counts_for_power_but_sets_no_time_or_speed(self):
        self.post(self.client_a, "/rides", _ride())
        windy = _ride(duration_s=1100, max_speed_kmh=60, peak_5s_w=700, wind_ms=8, wind_from_deg=315)
        saved = self.post(self.client_a, "/rides", windy).json()
        # a wind behind the rider is no record of theirs; their power is
        self.assertEqual(saved["records"], ["peak_5s_w"])
        self.assertEqual((saved["ride"]["wind_ms"], saved["ride"]["wind_from_deg"]), (8, 315))
        summary = self.client_a.get(f"{API}/records").json()
        self.assertEqual(summary["routes"][0]["duration_s"], 1500)
        self.assertEqual(summary["max_speed_kmh"], 41.2)
        self.assertEqual(summary["peaks"]["peak_5s_w"], 700)
        self.assertEqual(self.client_a.get(f"{API}/rides").json()[0]["wind_ms"], 8)

    def test_the_first_race_without_wind_on_a_route_is_its_first_result(self):
        self.post(self.client_a, "/rides", _ride(wind_ms=5))
        self.assertEqual(self.post(self.client_a, "/rides", _ride(duration_s=1700)).json()["records"], ["route_first"])

    def test_a_wind_is_a_speed_and_a_bearing(self):
        self.assertEqual(self.post(self.client_a, "/rides", _ride(wind_ms=30)).status_code, 201)
        self.assertEqual(self.post(self.client_a, "/rides", _ride(wind_ms=31)).status_code, 422)
        self.assertEqual(self.post(self.client_a, "/rides", _ride(wind_ms=5, wind_from_deg=360)).status_code, 422)

    def test_the_profile_marks_a_ride_ridden_with_wind(self):
        self.post(self.client_a, "/rides", _ride(wind_ms=6))
        with translation_override("en"):
            self.assertContains(self.client_a.get(reverse("account_profile")), ", " + gettext("wind") + "</span>")

    def test_records_sum_up_every_ride_and_keep_the_best_per_route(self):
        self.post(self.client_a, "/rides", _ride())
        self.post(self.client_a, "/rides", _ride(duration_s=1450))
        self.post(self.client_a, "/rides", _ride(route="medeu", route_name="Medeu climb", duration_s=2400))
        self.post(self.client_a, "/rides", _ride(kind="free", duration_s=3600, distance_m=30000))
        summary = self.client_a.get(f"{API}/records").json()
        self.assertEqual(summary["rides"], 4)
        self.assertEqual(summary["distance_km"], round((10600 * 3 + 30000) / 1000, 1))
        routes = {r["route"]: r for r in summary["routes"]}
        self.assertEqual(routes["center"]["duration_s"], 1450)
        self.assertEqual(routes["center"]["attempts"], 2)
        self.assertEqual(routes["medeu"]["route_name"], "Medeu climb")

    def test_a_member_sees_and_deletes_only_their_own_rides(self):
        other = _user("boris")
        mine = self.post(self.client_a, "/rides", _ride()).json()["ride"]["id"]
        theirs = self.post(self.member(other), "/rides", _ride()).json()["ride"]["id"]
        listed = [r["id"] for r in self.client_a.get(f"{API}/rides").json()]
        self.assertEqual(listed, [mine])
        self.assertEqual(self.client_a.delete(f"{API}/rides/{theirs}").status_code, 404)
        self.assertEqual(self.client_a.delete(f"{API}/rides/{mine}").status_code, 204)
        self.assertFalse(VirtualRide.objects.filter(pk=mine).exists())

    def test_a_personal_api_token_works_as_everywhere_else(self):
        response = self.client.get(f"{API}/records", HTTP_AUTHORIZATION=f"Bearer {self.user.api_token}")
        self.assertEqual(response.status_code, 200)

    def test_nonsense_is_refused(self):
        self.assertEqual(self.post(self.client_a, "/rides", _ride(duration_s=-5)).status_code, 422)
        self.assertEqual(self.post(self.client_a, "/rides", _ride(route="Bad Route!")).status_code, 422)

    def test_the_profile_shows_the_best_time_of_each_route(self):
        self.post(self.client_a, "/rides", _ride(duration_s=1499))
        with translation_override("en"):
            url = reverse("account_profile")
            heading = gettext("Virtual rides")
        html = self.client_a.get(url).content.decode()
        self.assertIn('id="virtual-rides"', html)
        self.assertIn(heading, html)
        self.assertIn("Center loop", html)
        self.assertIn("24:59", html)

    def test_the_profile_counts_rides_in_the_reader_s_grammar(self):
        with translation_override("ru"):
            url = reverse("account_profile")
            one, few, many = (ngettext("ride", "rides", n) for n in (1, 3, 5))
            self.assertEqual(ngettext("ride", "rides", 21), one)  # Russian: twenty-one rides like one
        self.assertEqual(len({one, few, many}), 3)
        self.post(self.client_a, "/rides", _ride())
        self.assertInHTML(f'<div class="text-muted">{one}</div>', self.client_a.get(url).content.decode())
        for _more in range(2):
            self.post(self.client_a, "/rides", _ride())
        self.assertInHTML(f'<div class="text-muted">{few}</div>', self.client_a.get(url).content.decode())


class GroupRaceTests(MemberClientMixin, TestCase):
    def setUp(self):
        self.host, self.guest = _user("anna"), _user("boris")
        self.client_h, self.client_g = self.member(self.host), self.member(self.guest)

    def create(self, **kwargs):
        return self.post(self.client_h, "/groups", {"route": "center", "route_name": "Center loop", **kwargs})

    def test_a_host_gathers_a_race_and_others_see_it_and_join(self):
        created = self.create(start_in_s=60)
        self.assertEqual(created.status_code, 201)
        group_id = created.json()["id"]
        listed = self.client_g.get(f"{API}/groups").json()
        self.assertEqual([g["id"] for g in listed], [group_id])
        self.assertFalse(listed[0]["is_member"])
        joined = self.post(self.client_g, f"/groups/{group_id}/join").json()
        self.assertTrue(joined["is_member"])
        self.assertEqual({m["user_id"] for m in joined["members"]}, {self.host.pk, self.guest.pk})

    def test_a_race_keeps_its_host_s_wind_for_every_member(self):
        group_id = self.create(start_in_s=60, wind_ms=6, wind_from_deg=270).json()["id"]
        seen = self.post(self.client_g, f"/groups/{group_id}/join").json()
        self.assertEqual((seen["wind_ms"], seen["wind_from_deg"]), (6, 270))
        listed = self.client_g.get(f"{API}/groups").json()[0]
        self.assertEqual((listed["wind_ms"], listed["wind_from_deg"]), (6, 270))
        # without one, the race is ridden in still air
        GroupRide.objects.filter(pk=group_id).update(cancelled=True)
        calm = self.create(start_in_s=60).json()
        self.assertEqual(calm["wind_ms"], 0)

    def test_a_ride_of_a_race_keeps_the_race_s_wind_whatever_the_page_sends(self):
        group = GroupRide.objects.create(
            route="center", host=self.host, start_at=timezone.now() - timedelta(minutes=30), wind_ms=7, wind_from_deg=90
        )
        GroupRideMember.objects.create(group=group, user=self.guest)
        saved = self.post(self.client_g, "/rides", _ride(group_id=group.pk, wind_ms=0)).json()
        self.assertEqual((saved["ride"]["wind_ms"], saved["ride"]["wind_from_deg"]), (7, 90))
        # a wind behind the riders is no record of theirs
        self.assertNotIn("route_first", saved["records"])

    def test_a_host_s_races_start_an_hour_apart_at_least(self):
        self.create()
        self.assertEqual(self.create().status_code, 409)
        later = timezone.now() + timedelta(days=3)
        self.assertEqual(self.create(start_at=later.isoformat()).status_code, 201)
        self.assertEqual(self.create(start_at=(later + timedelta(minutes=59)).isoformat()).status_code, 409)
        self.assertEqual(self.create(start_at=(later + timedelta(minutes=61)).isoformat()).status_code, 201)

    def test_a_host_has_ten_races_waiting_at_most(self):
        # every member's lobby lists them all, every few seconds
        for day in range(1, 11):
            at = (timezone.now() + timedelta(days=day)).isoformat()
            self.assertEqual(self.create(start_at=at).status_code, 201, day)
        refused = self.create(start_at=(timezone.now() + timedelta(days=20)).isoformat())
        self.assertEqual(refused.status_code, 409)
        with translation_override("ru"):
            many = ngettext(
                "You already have %(n)d group race waiting to start",
                "You already have %(n)d group races waiting to start",
                10,
            )
        self.assertEqual(refused.json()["detail"], many % {"n": 10})

    def test_a_race_is_gathered_for_a_date_and_time_up_to_a_year_ahead(self):
        at = (timezone.now() + timedelta(days=200)).replace(microsecond=0)
        created = self.create(start_at=at.isoformat())
        self.assertEqual(created.status_code, 201)
        self.assertEqual(GroupRide.objects.get(pk=created.json()["id"]).start_at, at)
        # others join it long before it starts, and it is listed meanwhile
        self.assertEqual(self.post(self.client_g, f"/groups/{created.json()['id']}/join").status_code, 200)
        self.assertEqual([g["id"] for g in self.client_g.get(f"{API}/groups").json()], [created.json()["id"]])

    def test_a_start_too_soon_too_late_or_without_its_time_zone_is_refused(self):
        now = timezone.now()
        for at in (now + timedelta(seconds=5), now + timedelta(days=366), now - timedelta(hours=1)):
            self.assertEqual(self.create(start_at=at.isoformat()).status_code, 422, at)
        self.assertEqual(self.create(start_at="2027-03-01T19:00:00").status_code, 422)

    def test_a_member_joins_races_on_different_days(self):
        first = self.create(start_at=(timezone.now() + timedelta(days=1)).isoformat()).json()["id"]
        second = self.create(start_at=(timezone.now() + timedelta(days=8)).isoformat()).json()["id"]
        for group_id in (first, second):
            self.assertTrue(self.post(self.client_g, f"/groups/{group_id}/join").json()["is_member"])

    def test_the_start_cannot_be_too_soon(self):
        self.assertEqual(self.create(start_in_s=5).status_code, 422)

    def test_nobody_joins_a_race_that_has_started(self):
        group = GroupRide.objects.create(route="center", host=self.host, start_at=timezone.now() - timedelta(seconds=5))
        self.assertEqual(self.post(self.client_g, f"/groups/{group.pk}/join").status_code, 409)

    def test_a_host_who_leaves_hands_the_race_on_and_alone_cancels_it(self):
        group_id = self.create().json()["id"]
        self.post(self.client_g, f"/groups/{group_id}/join")
        left = self.post(self.client_h, f"/groups/{group_id}/leave").json()
        # the guest still rides it, now as its host; the old host is out
        self.assertEqual((left["cancelled"], left["host"]["user_id"]), (False, self.guest.pk))
        self.assertEqual([m["user_id"] for m in left["members"]], [self.guest.pk])
        alone = self.post(self.client_g, f"/groups/{group_id}/leave").json()
        self.assertTrue(alone["cancelled"])

    def patch(self, client, path, data):
        return client.patch(f"{API}{path}", data=json.dumps(data), content_type="application/json")

    def test_the_host_changes_the_race_s_wind_until_its_start_and_nobody_else_does(self):
        """Made in the host's wind of the moment, a race kept it: its host -- or an admin -- now changes it before
        the start; the trainer's 30 m/s at most, as it is made with."""
        group_id = self.create(start_in_s=60, wind_ms=6, wind_from_deg=270).json()["id"]
        self.post(self.client_g, f"/groups/{group_id}/join")
        change = {"wind_ms": 12, "wind_from_deg": 90}
        self.assertEqual(self.patch(self.client_g, f"/groups/{group_id}", change).status_code, 403)
        changed = self.patch(self.client_h, f"/groups/{group_id}", change).json()
        self.assertEqual((changed["wind_ms"], changed["wind_from_deg"]), (12, 90))
        listed = self.client_g.get(f"{API}/groups").json()[0]
        self.assertEqual((listed["wind_ms"], listed["wind_from_deg"]), (12, 90))
        too_strong = self.patch(self.client_h, f"/groups/{group_id}", {"wind_ms": 31, "wind_from_deg": 0})
        self.assertEqual(too_strong.status_code, 422)
        admin = self.member(_user("vera", role=User.Role.ADMIN))
        self.assertEqual(self.patch(admin, f"/groups/{group_id}", {"wind_ms": 0, "wind_from_deg": 0}).status_code, 200)
        # once it has started, its riders keep the wind they started in
        GroupRide.objects.filter(pk=group_id).update(start_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.patch(self.client_h, f"/groups/{group_id}", change).status_code, 409)

    def test_only_the_host_cancels_and_a_cancelled_race_disappears(self):
        group_id = self.create().json()["id"]
        self.post(self.client_g, f"/groups/{group_id}/join")
        self.assertEqual(self.post(self.client_g, f"/groups/{group_id}/cancel").status_code, 403)
        self.assertEqual(self.post(self.client_h, f"/groups/{group_id}/cancel").status_code, 200)
        self.assertEqual(self.client_g.get(f"{API}/groups").json(), [])

    def test_deleting_a_ride_of_a_group_race_moves_the_others_up(self):
        group_id = self.create().json()["id"]
        self.post(self.client_g, f"/groups/{group_id}/join")
        self.post(self.client_h, "/rides", _ride(group_id=group_id, duration_s=1520))
        winner = self.post(self.client_g, "/rides", _ride(group_id=group_id, duration_s=1490)).json()["ride"]["id"]
        self.assertEqual(self.client_g.delete(f"{API}/rides/{winner}").status_code, 204)
        self.assertEqual(VirtualRide.objects.get(user=self.host).place, 1)

    def test_a_shared_link_leads_to_the_site_s_page_which_hands_out_the_cookie_to_join(self):
        # the trainer file opened on its own has no CSRF cookie, and a newcomer could not join from it
        for client in (self.client, self.client_g):
            self.assertEqual(client.get(f"{API}/me").json()["page_url"], reverse("virtual_ride"))

    def test_a_shared_link_opens_the_race_and_says_when_it_was_cancelled(self):
        group_id = self.create().json()["id"]
        opened = self.client_g.get(f"{API}/groups/{group_id}").json()
        self.assertEqual((opened["id"], opened["cancelled"], opened["is_member"]), (group_id, False, False))
        self.post(self.client_h, f"/groups/{group_id}/cancel")
        self.assertTrue(self.client_g.get(f"{API}/groups/{group_id}").json()["cancelled"])
        self.assertEqual(self.client_g.get(f"{API}/groups/{group_id + 1000}").status_code, 404)
        self.assertEqual(self.client.get(f"{API}/groups/{group_id}").status_code, 401)

    def test_results_put_the_fastest_finisher_first_and_only_members_may_post_to_a_race(self):
        group_id = self.create().json()["id"]
        outsider = _user("carl")
        self.assertEqual(self.post(self.member(outsider), "/rides", _ride(group_id=group_id)).status_code, 403)
        self.post(self.client_g, f"/groups/{group_id}/join")
        self.post(self.client_h, "/rides", _ride(group_id=group_id, duration_s=1520))
        self.post(self.client_g, "/rides", _ride(group_id=group_id, duration_s=1490))
        results = self.client_h.get(f"{API}/groups/{group_id}/results").json()
        self.assertEqual([r["user_id"] for r in results["finished"]], [self.guest.pk, self.host.pk])

    def test_places_in_a_group_race_come_from_the_saved_times_not_from_the_pages(self):
        group_id = self.create().json()["id"]
        self.post(self.client_g, f"/groups/{group_id}/join")
        # Each page thought it rode alone and claimed first place.
        first = self.post(self.client_h, "/rides", _ride(group_id=group_id, duration_s=1520, place=1, field_size=1))
        self.assertEqual((first.json()["ride"]["place"], first.json()["ride"]["field_size"]), (1, 2))
        self.post(self.client_g, "/rides", _ride(group_id=group_id, duration_s=1490, place=1, field_size=1))
        places = dict(VirtualRide.objects.filter(group_id=group_id).values_list("user_id", "place"))
        self.assertEqual(places, {self.guest.pk: 1, self.host.pk: 2})

    def test_a_time_trial_under_way_keeps_its_order(self):
        # a rider gone from it would bring every later rider's start forward, some into the past
        trial = GroupRide.objects.create(
            route="center", host=self.host, mode=GroupRide.Mode.ITT, start_at=timezone.now() - timedelta(seconds=5)
        )
        for user in (self.host, self.guest):
            GroupRideMember.objects.create(group=trial, user=user)
        left = self.post(self.client_h, f"/groups/{trial.pk}/leave")
        self.assertEqual(left.status_code, 409)
        self.assertEqual(trial.memberships.count(), 2)

    def test_a_ride_together_names_no_winner(self):
        group_id = self.create(kind="ride").json()["id"]
        self.post(self.client_g, f"/groups/{group_id}/join")
        # each page claimed first place
        self.post(self.client_h, "/rides", _ride(group_id=group_id, duration_s=1520, place=1, field_size=1))
        self.post(self.client_g, "/rides", _ride(group_id=group_id, duration_s=1490, place=1, field_size=1))
        places = set(VirtualRide.objects.filter(group_id=group_id).values_list("place", "field_size"))
        self.assertEqual(places, {(None, None)})


class FinishingTogetherTests(MemberClientMixin, TransactionTestCase):
    def test_two_members_finishing_at_once_get_different_places(self):
        host, guest = _user("anna"), _user("boris")
        group = GroupRide.objects.create(route="center", host=host, start_at=timezone.now())
        for user in (host, guest):
            GroupRideMember.objects.create(group=group, user=user)
        clients = {host.pk: self.member(host), guest.pk: self.member(guest)}
        ranked, go = threading.Event(), threading.Event()
        rank = records.rank_group

        def rank_then_hold(group):
            rank(group)
            if not ranked.is_set():
                ranked.set()
                go.wait(timeout=10)  # the first finisher's save is still open

        def save(user, seconds):
            try:
                self.post(clients[user.pk], "/rides", _ride(group_id=group.pk, duration_s=seconds))
            finally:
                connections.close_all()

        with mock.patch.object(records, "rank_group", side_effect=rank_then_hold):
            first = threading.Thread(target=save, args=(host, 1520))
            first.start()
            self.assertTrue(ranked.wait(timeout=10))
            second = threading.Thread(target=save, args=(guest, 1490))
            second.start()
            second.join(timeout=1)
            go.set()
            first.join(timeout=10)
            second.join(timeout=10)
        places = dict(VirtualRide.objects.values_list("user_id", "place"))
        self.assertEqual(places, {guest.pk: 1, host.pk: 2})


class RidingTogetherTests(MemberClientMixin, TestCase):
    def setUp(self):
        self.anna, self.boris = _user("anna"), _user("boris")
        self.client_a, self.client_b = self.member(self.anna), self.member(self.boris)

    def ride(self, client, **state):
        body = {"status": "ride", "route": "center", "mode": "free", "distance_m": 100, "speed_ms": 8, **state}
        return self.post(client, "/presence", body).json()

    def test_a_rider_on_a_race_s_line_is_told_of_its_wind_until_the_start(self):
        group_id = self.post(self.client_b, "/groups", {"route": "center", "start_in_s": 60}).json()["id"]
        self.post(self.client_a, f"/groups/{group_id}/join")
        change = json.dumps({"wind_ms": 9, "wind_from_deg": 180})
        self.client_b.patch(f"{API}/groups/{group_id}", data=change, content_type="application/json")
        seen = self.ride(self.client_a, group_id=group_id, mode="race")["groups"]
        self.assertEqual([(g["id"], g["wind_ms"], g["wind_from_deg"]) for g in seen], [(group_id, 9, 180)])
        # under way, the lobby's races stay away from a rider
        GroupRide.objects.filter(pk=group_id).update(start_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.ride(self.client_a, group_id=group_id, mode="race")["groups"], [])

    def test_the_lobby_lists_who_is_here_and_the_open_races(self):
        self.post(self.client_b, "/presence", {"status": "lobby", "route": "center"})
        self.post(self.client_b, "/groups", {"route": "center"})
        body = self.post(self.client_a, "/presence", {"status": "lobby", "route": "center"}).json()
        self.assertEqual([o["user_id"] for o in body["online"]], [self.boris.pk])
        self.assertEqual(len(body["groups"]), 1)
        self.assertEqual(body["riders"], [])

    def test_the_lobby_asks_the_database_as_often_for_many_races_as_for_one(self):
        def asked(hosts):
            for host in hosts:
                self.post(self.member(host), "/groups", {"route": "center"})
            with CaptureQueriesContext(connection) as queries:
                self.post(self.client_a, "/presence", {"status": "lobby", "route": "center"})
            return len(queries)

        asked([])  # the rider's own row made, as every later call finds it
        one = asked([_user("host0")])
        self.assertEqual(asked([_user(f"host{k}") for k in range(1, 5)]), one)

    def test_the_lobby_lists_the_others_in_a_steady_order(self):
        client_c = self.member(carl := _user("carl"))
        for client in (self.client_a, client_c, self.client_a):  # anna's row is rewritten last
            self.post(client, "/presence")
        online = self.post(self.client_b, "/presence").json()["online"]
        self.assertEqual([p["user_id"] for p in online], [self.anna.pk, carl.pk])

    def test_free_riders_on_the_same_route_see_each_other(self):
        self.ride(self.client_b, distance_m=250, cadence_rpm=90, power_w=210)
        riders = self.ride(self.client_a)["riders"]
        self.assertEqual(len(riders), 1)
        self.assertEqual(riders[0]["user_id"], self.boris.pk)
        self.assertEqual(riders[0]["distance_m"], 250)
        self.assertEqual(riders[0]["power_w"], 210)

    def test_a_different_route_or_a_solo_race_shows_nobody(self):
        self.ride(self.client_b, route="medeu")
        self.assertEqual(self.ride(self.client_a)["riders"], [])
        self.ride(self.client_b)
        self.assertEqual(self.ride(self.client_a, mode="race")["riders"], [])

    def test_a_group_race_shows_only_its_members(self):
        group = GroupRide.objects.create(route="center", host=self.anna, start_at=timezone.now())
        GroupRideMember.objects.create(group=group, user=self.anna)
        GroupRideMember.objects.create(group=group, user=self.boris)
        carl = _user("carl")
        self.ride(self.member(carl))  # a free rider on the same route stays out of the race
        self.ride(self.client_b, mode="race", group_id=group.pk)
        riders = self.ride(self.client_a, mode="race", group_id=group.pk)["riders"]
        self.assertEqual([r["user_id"] for r in riders], [self.boris.pk])

    def test_someone_who_closed_the_page_drops_out(self):
        self.ride(self.client_b)
        LiveRider.objects.filter(user=self.boris).update(
            updated_at=timezone.now() - timedelta(seconds=ONLINE_SECONDS + 1)
        )
        body = self.ride(self.client_a)
        self.assertEqual(body["riders"], [])
        self.assertEqual(body["online"], [])

    def test_a_group_the_rider_is_not_in_is_ignored(self):
        group = GroupRide.objects.create(route="center", host=self.boris, start_at=timezone.now())
        self.ride(self.client_a, mode="race", group_id=group.pk)
        self.assertIsNone(LiveRider.objects.get(user=self.anna).group_id)
