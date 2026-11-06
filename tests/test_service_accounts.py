"""The accounts the site's own agents post through (issue #436): the owners mark them in their profile or
through the API, and every page asks them to until one is marked."""

import uuid
from http import HTTPStatus

from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from accounts.models import User
from registrations.tests import make_user
from tests.test_virtual_members import _bearer

API = "/api/v1/service-accounts"


def _url(name):
    with translation.override("en"):
        return reverse(name)


class ServiceAccountTests(TestCase):
    def setUp(self):
        self.owner = make_user("owner", role=User.Role.OWNER, first_name="Site", last_name="Owner")
        self.admin = make_user("admin", role=User.Role.ADMIN)
        self.agent = make_user("agent", first_name="Events", last_name="Agent", api_token=uuid.uuid4())
        self.member = make_user("member")  # no token: an agent cannot post through it

    def test_until_one_is_marked_every_page_asks_the_owners_and_nobody_else(self):
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(_url("news_index")), "service-account-missing")
        self.client.force_login(self.admin)
        self.assertNotContains(self.client.get(_url("news_index")), "service-account-missing")
        User.objects.filter(pk=self.agent.pk).update(is_service_account=True)
        self.client.force_login(self.owner)
        self.assertNotContains(self.client.get(_url("news_index")), "service-account-missing")

    def test_the_owner_marks_exactly_the_ticked_accounts_among_those_with_a_token(self):
        self.client.force_login(self.owner)
        page = self.client.get(_url("account_profile"))
        self.assertContains(page, f'id="service-{self.agent.pk}"')
        self.assertNotContains(page, f'id="service-{self.member.pk}"')
        self.client.post(_url("account_service_accounts"), {"account": [self.agent.pk, self.member.pk]})
        self.assertEqual(set(User.objects.filter(is_service_account=True)), {self.agent})
        self.client.post(_url("account_service_accounts"), {})
        self.assertFalse(User.objects.filter(is_service_account=True).exists())

    def test_nobody_but_an_owner_sees_the_card_or_marks_an_account(self):
        self.client.force_login(self.admin)
        self.assertNotContains(self.client.get(_url("account_profile")), 'id="service-accounts"')
        refused = self.client.post(_url("account_service_accounts"), {"account": [self.agent.pk]})
        self.assertEqual(refused.status_code, HTTPStatus.FORBIDDEN)
        self.agent.refresh_from_db()
        self.assertFalse(self.agent.is_service_account)

    def test_the_api_lists_marks_and_unmarks_for_the_owners_alone(self):
        owner = _bearer(self.owner)
        listed = {row["user_id"]: row["service"] for row in self.client.get(f"{API}/", **owner).json()}
        self.assertEqual(listed.get(self.agent.pk), False)
        self.assertNotIn(self.member.pk, listed)
        self.assertEqual(self.client.put(f"{API}/{self.agent.pk}", **owner).status_code, HTTPStatus.NO_CONTENT)
        self.agent.refresh_from_db()
        self.assertTrue(self.agent.is_service_account)
        self.assertEqual(self.client.delete(f"{API}/{self.agent.pk}", **owner).status_code, HTTPStatus.NO_CONTENT)
        self.agent.refresh_from_db()
        self.assertFalse(self.agent.is_service_account)
        self.assertEqual(self.client.put(f"{API}/{self.member.pk}", **owner).status_code, HTTPStatus.NOT_FOUND)
        admin = _bearer(self.admin)
        self.assertEqual(self.client.put(f"{API}/{self.agent.pk}", **admin).status_code, HTTPStatus.FORBIDDEN)
