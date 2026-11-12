"""Changing the address a member signs in with (allauth's change mode, ACCOUNT_CHANGE_EMAIL).

The new address replaces the old one only once it is confirmed through the link sent to it. Until
then the old one still signs in, so a typo never locks anybody out, and an address another account
has confirmed is never taken over.
"""

import re

from allauth.account.models import EmailAddress
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from accounts.models import User

PASSWORD = "Strong-pass-2026"


class ChangeEmailTests(TestCase):
    def setUp(self):
        self.member = self._member("mover", "old@example.com", verified=True, role=User.Role.PARTICIPANT)
        self.client.force_login(self.member)

    @staticmethod
    def _member(username, address, verified, role=User.Role.GUEST):
        user = User.objects.create_user(username=username, email=address, password=PASSWORD, role=role)
        EmailAddress.objects.create(user=user, email=address, verified=verified, primary=True)
        return user

    def _ask_for(self, address):
        self.client.post(reverse("account_email"), {"action_add": "", "email": address})
        self.assertEqual(mail.outbox[-1].to, [address])

    def _open_the_link(self):
        key = re.search(r"/accounts/confirm-email/([^/\s]+)/", mail.outbox[-1].body).group(1)
        return self.client.post(reverse("account_confirm_email", args=[key]), follow=True)

    def _addresses(self, user):
        rows = EmailAddress.objects.filter(user=user).order_by("email")
        return list(rows.values_list("email", "primary", "verified"))

    def _signs_in(self, address):
        self.client.logout()
        response = self.client.post(reverse("account_login"), {"login": address, "password": PASSWORD})
        return response.status_code == 302

    def test_until_the_new_address_is_confirmed_the_old_one_stays(self):
        self._ask_for("new@example.com")
        self.member.refresh_from_db()
        self.assertEqual(self.member.email, "old@example.com")
        self.assertIn(("old@example.com", True, True), self._addresses(self.member))
        self.assertTrue(self._signs_in("old@example.com"))

    def test_once_confirmed_the_new_address_replaces_the_old_one(self):
        self._ask_for("new@example.com")
        self._open_the_link()
        self.member.refresh_from_db()
        self.assertEqual(self.member.email, "new@example.com")
        self.assertEqual(self._addresses(self.member), [("new@example.com", True, True)])
        self.assertTrue(self._signs_in("new@example.com"))
        self.assertFalse(self._signs_in("old@example.com"))

    def test_a_change_cancelled_before_it_is_confirmed_leaves_the_old_address(self):
        self._ask_for("new@example.com")
        self.client.post(reverse("account_email"), {"action_remove": "", "email": "new@example.com"})
        self._open_the_link()
        self.member.refresh_from_db()
        self.assertEqual(self.member.email, "old@example.com")
        self.assertEqual(self._addresses(self.member), [("old@example.com", True, True)])

    def test_a_guest_who_mistyped_the_address_puts_it_right_and_becomes_a_participant(self):
        guest = self._member("typist", "typo@exampel.com", verified=False)
        self.client.force_login(guest)
        self._ask_for("right@example.com")
        self._open_the_link()
        guest.refresh_from_db()
        self.assertEqual(guest.email, "right@example.com")
        self.assertEqual(self._addresses(guest), [("right@example.com", True, True)])
        self.assertEqual(guest.role, User.Role.PARTICIPANT)

    def test_an_address_another_account_confirmed_is_not_taken_over(self):
        other = self._member("owner-of-it", "taken@example.com", verified=True, role=User.Role.PARTICIPANT)
        self._ask_for("taken@example.com")
        self._open_the_link()
        self.member.refresh_from_db()
        self.assertEqual(self.member.email, "old@example.com")
        self.assertEqual(self._addresses(other), [("taken@example.com", True, True)])
