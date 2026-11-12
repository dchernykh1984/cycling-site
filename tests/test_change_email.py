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
from django.utils.translation import gettext

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

    def test_a_guest_waiting_for_the_new_address_can_still_change_it_from_the_profile(self):
        # allauth clears an unconfirmed address as soon as another is asked for, so user.email is empty.
        guest = self._member("waiting", "typo@exampel.com", verified=False)
        self.client.force_login(guest)
        self._ask_for("rihgt@example.com")
        page = self.client.get(reverse("account_profile")).content.decode()
        url, label = re.escape(reverse("account_email")), re.escape(gettext("Change email"))
        self.assertRegex(page, rf'href="{url}"[^>]*>\s*{label}\s*</a>')

    def test_the_page_names_the_waiting_address_apart_from_the_field_for_another(self):
        EmailAddress.objects.create(user=self.member, email="new@example.com", verified=False, primary=False)
        for language in ("ru", "kk", "en"):
            with self.subTest(language=language):
                page = self.client.get(f"/{language}/accounts/email/").content.decode()
                labels = [" ".join(label.split()) for label in re.findall(r"<label[^>]*>(.*?)</label>", page, re.S)]
                self.assertEqual(len(labels), len(set(labels)), labels)

    def test_the_change_page_has_one_main_action(self):
        EmailAddress.objects.create(user=self.member, email="new@example.com", verified=False, primary=False)
        page = self.client.get(reverse("account_email")).content.decode()
        actions = [tag for tag in re.findall(r"<button\b[^>]*>", page) if 'name="action_' in tag]
        self.assertEqual(sum("btn-primary" in tag for tag in actions), 1, actions)

    def test_an_address_written_without_allauth_shows_and_changes_like_any_other(self):
        # createsuperuser and the admin keep no allauth record of the address (the owner's account is one);
        # allauth makes it, unconfirmed, as the page opens.
        owner = User.objects.create_user(
            username="boss", email="Boss@example.com", password=PASSWORD, role=User.Role.OWNER
        )
        self.client.force_login(owner)
        page = self.client.get(reverse("account_email")).content.decode()
        self.assertIn('value="boss@example.com"', page)
        self.assertNotIn(gettext("Warning:"), page)
        self._ask_for("new@example.com")
        self._open_the_link()
        owner.refresh_from_db()
        self.assertEqual(owner.email, "new@example.com")
        self.assertEqual(self._addresses(owner), [("new@example.com", True, True)])

    def test_an_address_another_account_confirmed_is_not_taken_over(self):
        other = self._member("owner-of-it", "taken@example.com", verified=True, role=User.Role.PARTICIPANT)
        self._ask_for("taken@example.com")
        self._open_the_link()
        self.member.refresh_from_db()
        self.assertEqual(self.member.email, "old@example.com")
        self.assertEqual(self._addresses(other), [("taken@example.com", True, True)])
