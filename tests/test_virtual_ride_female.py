"""A woman's profile, as the virtual ride page learns it: her own figure and word, and the others' pages drawing her."""

from django.test import TestCase

from accounts.models import User
from tests.test_virtual_ride_api import API, MemberClientMixin, _ride, _user


class WomanOnTheRideTests(MemberClientMixin, TestCase):
    def setUp(self):
        self.anna = _user("anna", gender=User.Gender.FEMALE)
        self.boris = _user("boris", gender=User.Gender.MALE)
        self.carl = _user("carl")  # no gender in the profile
        self.client_a, self.client_b = self.member(self.anna), self.member(self.boris)

    def test_me_says_whether_the_profile_names_a_woman(self):
        for user, female in ((self.anna, True), (self.boris, False), (self.carl, False)):
            with self.subTest(user=user.username):
                self.assertIs(self.member(user).get(f"{API}/me").json()["female"], female)

    def test_the_others_on_the_route_learn_she_is_a_woman(self):
        ride = {"status": "ride", "route": "center", "mode": "free", "distance_m": 100, "speed_ms": 8}
        self.post(self.client_a, "/presence", ride)
        riders = self.post(self.client_b, "/presence", ride).json()["riders"]
        self.assertEqual([(r["user_id"], r["female"]) for r in riders], [(self.anna.pk, True)])

    def test_a_race_s_results_say_who_is_a_woman(self):
        group_id = self.post(self.client_b, "/groups", {"route": "center", "start_in_s": 60}).json()["id"]
        self.post(self.client_a, f"/groups/{group_id}/join")
        self.post(self.client_a, "/rides", _ride(group_id=group_id, duration_s=1490))
        self.post(self.client_b, "/rides", _ride(group_id=group_id, duration_s=1520))
        finished = self.client_b.get(f"{API}/groups/{group_id}/results").json()["finished"]
        self.assertEqual(
            [(r["user_id"], r["female"]) for r in finished], [(self.anna.pk, True), (self.boris.pk, False)]
        )
