"""/api/v1/managing/ (issue #315): the profile's two sections as API operations, with the same rules."""

import datetime
import uuid

from django.conf import settings
from django.test import TestCase
from django.utils import timezone, translation
from django.utils.translation import gettext

from accounts import managing
from accounts.models import ManagedMember, ManagerInvite, User
from api.tests import ApiTestMixin

API = "/api/v1/managing"


def _said(text, **names):
    """What the API says, in the site's language: a client that names no language gets that one."""
    with translation.override(settings.LANGUAGE_CODE):
        return gettext(text) % names


def _user(username, **kwargs):
    kwargs.setdefault("role", User.Role.PARTICIPANT)
    return User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pw", api_token=uuid.uuid4(), **kwargs
    )


class ManagingApiTests(ApiTestMixin, TestCase):
    def setUp(self):
        self.coach = _user("coach", first_name="Ivan", last_name="Petrov")
        self.anna = _user(
            "anna",
            first_name="Anna",
            last_name="Ivanova",
            team="Snow Leopards",
            city="Taraz",
            gender=User.Gender.FEMALE,
            birth_date=datetime.date(2009, 4, 17),
        )

    def _join(self, member, key):
        return self.post(f"{API}/join", {"key": str(key)}, user=member)

    def test_every_operation_needs_a_confirmed_member(self):
        guest = _user("guest", role=User.Role.GUEST)
        self.client.force_login(guest)
        calls = [
            ("get", "/"),
            ("post", "/invite"),
            ("delete", "/invite"),
            ("post", "/join"),
            ("post", "/waiting/accept-all"),
            ("post", "/waiting/reject-all"),
            ("post", f"/waiting/{self.anna.pk}/accept"),
            ("post", f"/waiting/{self.anna.pk}/reject"),
            ("delete", f"/members/{self.anna.pk}"),
            ("delete", f"/managers/{self.coach.pk}"),
        ]
        for method, path in calls:
            with self.subTest(f"{method} {path}"):
                response = getattr(self.client, method)(f"{API}{path}", content_type="application/json")
                self.assertEqual(response.status_code, 401)

    def test_the_site_session_of_a_confirmed_member_will_do(self):
        self.client.force_login(self.coach)
        self.assertEqual(self.client.post(f"{API}/invite").status_code, 201)

    def test_the_link_is_made_made_new_and_deleted(self):
        self.assertIsNone(self.get(f"{API}/", user=self.coach).json()["invite"])
        first = self.post(f"{API}/invite", {}, user=self.coach).json()
        self.assertIn(f"/accounts/managing/join/{first['key']}/", first["url"])
        self.assertEqual(self.get(f"{API}/", user=self.coach).json()["invite"]["key"], first["key"])
        second = self.post(f"{API}/invite", {}, user=self.coach).json()
        self.assertNotEqual(second["key"], first["key"])
        self.assertEqual(self._join(self.anna, first["key"]).status_code, 404)
        self.assertEqual(self.delete(f"{API}/invite", user=self.coach).status_code, 204)
        self.assertIsNone(self.get(f"{API}/", user=self.coach).json()["invite"])

    def test_a_link_run_out_is_not_listed_and_lets_nobody_in(self):
        key = managing.issue_invite(self.coach).key
        ManagerInvite.objects.update(created_at=timezone.now() - ManagerInvite.LIFETIME)
        self.assertIsNone(self.get(f"{API}/", user=self.coach).json()["invite"])
        response = self._join(self.anna, key)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["detail"],
            _said("This link is not valid or has probably expired. Ask whoever sent it for a new one."),
        )

    def test_asking_waits_and_each_reason_not_to_is_told(self):
        key = managing.issue_invite(self.coach).key
        response = self._join(self.anna, key)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"user_id": self.coach.pk, "name": "Ivan Petrov", "waiting": True})
        again = self._join(self.anna, key)
        self.assertEqual(again.status_code, 409)
        self.assertEqual(
            again.json()["detail"],
            _said("Your request to %(name)s is already waiting to be accepted.", name="Ivan Petrov"),
        )
        own = self._join(self.coach, key)
        self.assertEqual(own.status_code, 409)
        self.assertEqual(
            own.json()["detail"],
            _said("This is your own link: send it to the people whose registrations and photos you will manage."),
        )
        managing.accept(self.coach, self.anna.pk)
        self.assertEqual(
            self._join(self.anna, key).json()["detail"],
            _said("%(name)s already manages your registrations and photos.", name="Ivan Petrov"),
        )
        self.assertEqual(self._join(self.anna, uuid.uuid4()).status_code, 404)

    def test_a_request_shows_what_tells_the_member_apart_and_a_member_the_form_data_and_no_email(self):
        managing.ask(self.anna, managing.issue_invite(self.coach).key)
        waiting = self.get(f"{API}/", user=self.coach).json()["waiting"]
        self.assertEqual(
            waiting,
            [
                {
                    "user_id": self.anna.pk,
                    "last_name": "Ivanova",
                    "first_name": "Anna",
                    "team": "Snow Leopards",
                    "birth_year": 2009,
                }
            ],
        )
        self.assertEqual(self.post(f"{API}/waiting/{self.anna.pk}/accept", {}, user=self.coach).status_code, 204)
        overview = self.get(f"{API}/", user=self.coach).json()
        self.assertEqual(overview["waiting"], [])
        self.assertEqual(
            overview["members"],
            [
                {
                    "user_id": self.anna.pk,
                    "last_name": "Ivanova",
                    "first_name": "Anna",
                    "birth_date": "2009-04-17",
                    "gender": "F",
                    "city": "Taraz",
                    "team": "Snow Leopards",
                }
            ],
        )
        self.assertEqual(
            self.get(f"{API}/", user=self.anna).json()["managers"],
            [{"user_id": self.coach.pk, "name": "Ivan Petrov", "waiting": False}],
        )

    def test_requests_are_answered_one_by_one_or_all_at_once(self):
        key = managing.issue_invite(self.coach).key
        boris, carl = _user("boris"), _user("carl")
        for member in (self.anna, boris, carl):
            managing.ask(member, key)
        self.assertEqual(self.post(f"{API}/waiting/{boris.pk}/reject", {}, user=self.coach).status_code, 204)
        self.assertEqual(self.post(f"{API}/waiting/{boris.pk}/reject", {}, user=self.coach).status_code, 404)
        self.assertEqual(self.post(f"{API}/waiting/accept-all", {}, user=self.coach).json(), {"count": 2})
        self.assertEqual(managing.member_ids(self.coach), {self.anna.pk, carl.pk})
        managing.ask(boris, key)
        self.assertEqual(self.post(f"{API}/waiting/reject-all", {}, user=self.coach).json(), {"count": 1})
        self.assertEqual(self.post(f"{API}/waiting/{boris.pk}/accept", {}, user=self.coach).status_code, 404)

    def test_either_side_ends_it(self):
        key = managing.issue_invite(self.coach).key
        managing.ask(self.anna, key)
        managing.accept(self.coach, self.anna.pk)
        self.assertEqual(self.delete(f"{API}/members/{self.anna.pk}", user=self.coach).status_code, 204)
        self.assertEqual(self.delete(f"{API}/members/{self.anna.pk}", user=self.coach).status_code, 404)
        managing.ask(self.anna, key)
        self.assertEqual(self.delete(f"{API}/managers/{self.coach.pk}", user=self.anna).status_code, 204)
        managing.ask(self.anna, key)
        managing.accept(self.coach, self.anna.pk)
        self.assertEqual(self.delete(f"{API}/managers/{self.coach.pk}", user=self.anna).status_code, 204)
        self.assertFalse(ManagedMember.objects.exists())

    def test_an_id_in_the_address_reaches_only_the_callers_own_rows(self):
        managing.ask(self.anna, managing.issue_invite(self.coach).key)
        stranger = _user("stranger")
        self.assertEqual(self.post(f"{API}/waiting/{self.anna.pk}/accept", {}, user=stranger).status_code, 404)
        self.assertEqual(self.post(f"{API}/waiting/accept-all", {}, user=stranger).json(), {"count": 0})
        self.assertEqual(self.delete(f"{API}/managers/{self.coach.pk}", user=stranger).status_code, 404)
        self.assertEqual(self.delete(f"{API}/members/{self.anna.pk}", user=stranger).status_code, 404)
        self.assertIsNone(ManagedMember.objects.get().accepted_at)
        self.assertEqual(self.get(f"{API}/", user=stranger).json()["waiting"], [])
