"""Virtual ride on the site: saved rides and records in the profile, group races, riding together."""

import json
import threading
import uuid
from datetime import timedelta
from unittest import mock

from django.db import connections
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import override as translation_override

from accounts.models import User
from trainer import records
from trainer.live import ONLINE_SECONDS
from trainer.models import GroupRide, GroupRideMember, LiveRider, VirtualRide

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

    def test_one_waiting_race_per_host(self):
        self.create()
        self.assertEqual(self.create().status_code, 409)

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

    def test_only_the_host_cancels_and_a_cancelled_race_disappears(self):
        group_id = self.create().json()["id"]
        self.post(self.client_g, f"/groups/{group_id}/join")
        self.assertEqual(self.post(self.client_g, f"/groups/{group_id}/cancel").status_code, 403)
        self.assertEqual(self.post(self.client_h, f"/groups/{group_id}/cancel").status_code, 200)
        self.assertEqual(self.client_g.get(f"{API}/groups").json(), [])

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

    def test_the_lobby_lists_who_is_here_and_the_open_races(self):
        self.post(self.client_b, "/presence", {"status": "lobby", "route": "center"})
        self.post(self.client_b, "/groups", {"route": "center"})
        body = self.post(self.client_a, "/presence", {"status": "lobby", "route": "center"}).json()
        self.assertEqual([o["user_id"] for o in body["online"]], [self.boris.pk])
        self.assertEqual(len(body["groups"]), 1)
        self.assertEqual(body["riders"], [])

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
