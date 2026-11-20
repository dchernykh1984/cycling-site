"""Which language a mail about an account goes in.

Signed in as the account a mail is for, or signing it up just now, the visitor is the member who
reads it: the mail goes in the language of their profile, else of the page. A mail anybody could cause
about anybody's address -- a reset asked for without signing in -- goes in every language of the site,
each part with its links in its own language.
"""

import re

from allauth.account.models import EmailAddress
from django.conf import settings
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext

from accounts.models import User
from tests.language_urls import in_language

ADDRESS = "member@example.com"
PASSWORD = "Strong-pass-2026"
NEW_PASSWORD = "Another-pass-2026"
LANGUAGES = [code for code, _name in settings.LANGUAGES]
RESET_TEXT = (
    "You're receiving this email because you or someone else has requested a password reset for your user"
    " account.\nIt can be safely ignored if you did not request a password reset. Click the link below to"
    " reset your password."
)


def _in(code, msgid):
    with translation.override(code):
        return gettext(msgid)


def _in_every_language(msgid):
    return " / ".join(_in(code, msgid) for code in LANGUAGES)


def _reset_link(text):
    return re.search(r"https?://[^/\s]+(/\S+/password/reset/key/\S+/)", text).group(1)


class MailLanguageTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user(username="member", email=ADDRESS, password=PASSWORD)
        EmailAddress.objects.create(user=self.member, email=ADDRESS, verified=True, primary=True)

    def prefer(self, language):
        self.member.preferred_language = language
        self.member.save(update_fields=["preferred_language"])

    def change_password(self, page_language):
        self.client.force_login(self.member)
        self.client.post(
            in_language(reverse("account_change_password"), page_language),
            {"oldpassword": PASSWORD, "password1": NEW_PASSWORD, "password2": NEW_PASSWORD},
        )
        return mail.outbox[-1]

    def ask_for_a_reset(self, address=ADDRESS):
        self.client.post(in_language(reverse("account_reset_password"), "kk"), {"email": address})
        return mail.outbox[-1]

    def test_a_member_signed_in_reads_it_in_the_language_of_their_profile(self):
        self.prefer("kk")
        self.assertEqual(self.change_password("ru").subject, _in("kk", "Password Changed"))

    def test_without_a_language_in_the_profile_it_is_the_page_language(self):
        self.assertEqual(self.change_password("kk").subject, _in("kk", "Password Changed"))

    def test_a_reset_asked_for_without_signing_in_comes_in_every_language(self):
        self.prefer("kk")
        message = self.ask_for_a_reset()
        self.assertEqual(message.to, [ADDRESS])
        self.assertEqual(message.subject, _in_every_language("Password Reset Email"))
        parts = message.body.split("\n\n----------\n\n")
        self.assertEqual(len(parts), len(LANGUAGES))
        for code, part in zip(LANGUAGES, parts, strict=True):
            with self.subTest(language=code):
                self.assertIn(_in(code, RESET_TEXT), part)
                link = _reset_link(part)
                self.assertTrue(link.startswith(f"/{code}/"), link)
                self.assertFalse(self.client.get(link, follow=True).context.get("token_fail"))

    def test_a_reset_another_member_asks_for_comes_in_every_language(self):
        other = User.objects.create_user(username="other", email="other@example.com", password=PASSWORD)
        other.preferred_language = "ru"
        other.save(update_fields=["preferred_language"])
        self.client.force_login(other)
        self.assertEqual(self.ask_for_a_reset().subject, _in_every_language("Password Reset Email"))

    def test_the_notice_of_a_reset_done_without_signing_in_comes_in_every_language(self):
        form = self.client.get(_reset_link(self.ask_for_a_reset().body), follow=True)
        self.client.post(form.request["PATH_INFO"], {"password1": NEW_PASSWORD, "password2": NEW_PASSWORD})
        self.member.refresh_from_db()
        self.assertTrue(self.member.check_password(NEW_PASSWORD))
        self.assertEqual(mail.outbox[-1].subject, _in_every_language("Password Reset"))

    def test_a_sign_up_is_answered_in_the_page_language(self):
        self.client.post(
            in_language(reverse("account_signup"), "kk"),
            {"email": "new@example.com", "password1": PASSWORD, "password2": PASSWORD, "privacy": "on"},
        )
        self.assertEqual(mail.outbox[-1].subject, _in("kk", "Please Confirm Your Email Address"))

    def test_a_reset_for_an_address_without_an_account_comes_in_every_language(self):
        message = self.ask_for_a_reset("nobody@example.com")
        self.assertEqual(message.to, ["nobody@example.com"])
        self.assertEqual(message.subject, _in_every_language("Unknown Account"))
