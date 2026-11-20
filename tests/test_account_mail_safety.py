"""What a copy of the site's mail is worth to somebody who reads it: a reset link lasts an hour."""

import re
from datetime import datetime, timedelta
from unittest import mock

from allauth.account.models import EmailAddress
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from accounts.models import User

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
