"""A Kazakh reader meets no Russian on the account pages, in a form's errors or in a refused form.

django-allauth ships no Kazakh at all, and Django's own Kazakh lacks the password rules, most form
errors and the page that refuses a form sent without its security cookie, so every one of those
strings fell back to Russian, the site's default language: /kk/accounts/signup/ listed its password
rules and its errors in Russian under Kazakh labels. Each page here is held against the Russian of both
packages phrase by phrase, so a string a later release of either adds is caught as well.
"""

import functools
import html
import re
from pathlib import Path

import allauth
import django
import polib
from django.core import mail
from django.test import Client, TestCase
from django.utils import translation
from django.utils.translation import gettext

from accounts.models import User

CYRILLIC = re.compile(f"[{chr(0x0400)}-{chr(0x04FF)}]")


@functools.cache
def _russian_phrases() -> frozenset[str]:
    """Every phrase of twelve letters or more in the Russian catalogues of allauth and Django."""
    phrases = set()
    for package in (allauth, django):
        for catalogue in Path(package.__path__[0]).glob("**/locale/ru/LC_MESSAGES/django.po"):
            for entry in polib.pofile(str(catalogue)):
                for text in (entry.msgstr, *entry.msgstr_plural.values()):
                    for part in re.split(r"%\(\w+\)[sdr]|%[sd]|<[^>]+>|[.!?:;\n]", text):
                        part = " ".join(part.split()).strip(" ,\"'")
                        if len(part) >= 12 and CYRILLIC.search(part):
                            phrases.add(part)
    return frozenset(phrases)


def _russian_in(text: str) -> list[str]:
    words = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text)).split())
    return sorted(phrase for phrase in _russian_phrases() if phrase in words)


def _kazakh(msgid: str) -> str:
    with translation.override("kk"):
        return gettext(msgid)


class KazakhAccountPagesTests(TestCase):
    def assert_speaks_kazakh(self, response, *msgids):
        page = response.content.decode()
        self.assertEqual(_russian_in(page), [])
        for msgid in msgids:
            self.assertIn(_kazakh(msgid), html.unescape(page))

    def test_the_pages_a_guest_opens(self):
        for path in (
            "/kk/accounts/signup/",
            "/kk/accounts/login/",
            "/kk/accounts/password/reset/",
            "/kk/accounts/password/reset/done/",
            "/kk/accounts/confirm-email/",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assert_speaks_kazakh(response)

    def test_a_sign_up_that_gets_everything_wrong(self):
        response = self.client.post(
            "/kk/accounts/signup/", {"email": "not-an-address", "password1": "1234", "password2": "4321"}
        )
        self.assert_speaks_kazakh(
            response,
            "Enter a valid email address.",
            "This password is too common.",
            "This password is entirely numeric.",
        )

    def test_two_passwords_that_differ(self):
        response = self.client.post(
            "/kk/accounts/signup/",
            {"email": "kazakh.reader@example.com", "password1": "Strong-pass-2026", "password2": "Strong-pass-2027"},
        )
        self.assert_speaks_kazakh(response, "You must type the same password each time.")

    def test_a_password_too_like_the_address(self):
        """The rule names the field it compared with, so the field's own name needs Kazakh too."""
        response = self.client.post(
            "/kk/accounts/signup/",
            {"email": "kazakhreader@example.com", "password1": "kazakhreader1", "password2": "kazakhreader1"},
        )
        self.assert_speaks_kazakh(response, "email address")

    def test_the_confirmation_mail_after_a_sign_up(self):
        self.client.post(
            "/kk/accounts/signup/",
            {"email": "new.reader@example.com", "password1": "Strong-pass-2026", "password2": "Strong-pass-2026"},
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(_russian_in(mail.outbox[0].subject + "\n" + mail.outbox[0].body), [])

    def test_a_failed_sign_in_and_a_reset_for_a_bad_address(self):
        response = self.client.post("/kk/accounts/login/", {"login": "nobody@example.com", "password": "wrong-pass"})
        self.assert_speaks_kazakh(response, "The email address and/or password you specified are not correct.")
        response = self.client.post("/kk/accounts/password/reset/", {"email": "not-an-address"})
        self.assert_speaks_kazakh(response, "Enter a valid email address.")

    def test_the_pages_a_member_opens(self):
        user = User.objects.create_user(
            username="kk-member", email="kk.member@example.com", password="Strong-pass-2026"
        )
        self.client.force_login(user)
        for path in ("/kk/accounts/password/change/", "/kk/accounts/email/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assert_speaks_kazakh(response)

    def test_a_form_refused_for_a_missing_security_cookie(self):
        """A chat app's own browser can drop cookies, and the refusal is all such a reader sees."""
        client = Client(enforce_csrf_checks=True)
        response = client.post("/kk/accounts/login/", {"login": "a@example.com", "password": "x"})
        self.assertEqual(response.status_code, 403)
        self.assert_speaks_kazakh(response, "CSRF verification failed. Request aborted.")
        response = client.post("/kk/accounts/login/", {"login": "a@example.com", "password": "x"}, secure=True)
        self.assertEqual(response.status_code, 403)
        self.assert_speaks_kazakh(response, "CSRF verification failed. Request aborted.")
