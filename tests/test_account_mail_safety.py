"""The site's mail about signing in: a copy of a reset link is worth nothing after an hour, and a
change to how a member signs in is told to them, so a change they did not make is noticed."""

import re
from datetime import datetime, timedelta
from unittest import mock

from allauth.account.models import EmailAddress
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from tests.language_urls import in_language

ADDRESS = "member@example.com"


class ResetLinkTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user(username="member", email=ADDRESS, password="Strong-pass-2026")
        EmailAddress.objects.create(user=self.member, email=ADDRESS, verified=True, primary=True)

    def reset_link(self):
        self.client.post(reverse("account_reset_password"), {"email": ADDRESS})
        return re.search(r"https?://[^/\s]+(/\S*/password/reset/key/\S+/)", mail.outbox[-1].body).group(1)

    def opens(self, link, minutes_later):
        later = datetime.now() + timedelta(minutes=minutes_later)
        with mock.patch.object(PasswordResetTokenGenerator, "_now", return_value=later):
            # allauth names a link that no longer works; one that works opens the new password form
            return not self.client.get(link, follow=True).context.get("token_fail")

    def test_a_reset_link_lasts_an_hour(self):
        link = self.reset_link()
        self.assertTrue(self.opens(link, 59))
        self.assertFalse(self.opens(link, 61))


class ChangeNoticeTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user(username="member", email=ADDRESS, password="Strong-pass-2026")
        EmailAddress.objects.create(user=self.member, email=ADDRESS, verified=True, primary=True)
        self.client.force_login(self.member)

    def test_a_changed_password_is_told(self):
        self.client.post(
            in_language(reverse("account_change_password"), "en"),
            {"oldpassword": "Strong-pass-2026", "password1": "Another-pass-2026", "password2": "Another-pass-2026"},
        )
        notice = mail.outbox[-1]
        self.assertEqual((notice.to, notice.subject), ([ADDRESS], "Password Changed"))
        self.assertIn("Your password has been changed.", notice.body)

    def test_a_changed_address_is_told_at_the_old_one(self):
        self.client.post(in_language(reverse("account_email"), "en"), {"action_add": "", "email": "new@example.com"})
        key = re.search(r"/accounts/confirm-email/([^/\s]+)/", mail.outbox[-1].body).group(1)
        self.client.post(in_language(reverse("account_confirm_email", args=[key]), "en"))
        notice = mail.outbox[-1]
        self.assertEqual((notice.to, notice.subject), ([ADDRESS], "Email Changed"))
        self.assertIn(f"from {ADDRESS} to new@example.com", notice.body)
