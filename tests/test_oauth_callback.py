"""The address an OAuth provider sends a reader back to must not depend on their language.

Google and GitHub compare the ``redirect_uri`` against a list typed into their console by hand and
refuse anything that is not on it. With allauth's provider routes living only under
``i18n_patterns`` the reversed callback was /ru/..., /kk/... or /en/... depending on who was
signing in, so all three were addresses nobody had registered and everyone got
"Error 400: redirect_uri_mismatch". Strava went on working and hid it, because Strava validates
the callback *domain* rather than the path.
"""

import re
import urllib.parse

from django.test import TestCase, override_settings
from django.urls import resolve, reverse
from django.utils import translation

LANGUAGES = ("ru", "kk", "en")
PROVIDERS = ("google", "github", "strava")
_PREFIXED = re.compile(r"^/(?:ru|kk|en)/")

FAKE_APPS = {provider: {"APP": {"client_id": f"{provider}-client-id", "secret": "s"}} for provider in PROVIDERS}


class CallbackAddressTests(TestCase):
    def test_the_callback_address_does_not_change_with_the_language(self):
        for provider in PROVIDERS:
            for code in LANGUAGES:
                with self.subTest(provider=provider, language=code):
                    with translation.override(code):
                        path = reverse(f"{provider}_callback")
                    self.assertFalse(
                        _PREFIXED.match(path),
                        f"{provider} callback carries a language prefix: {path}",
                    )

    def test_every_provider_reverses_to_the_same_address_whatever_the_language(self):
        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                seen = set()
                for code in LANGUAGES:
                    with translation.override(code):
                        seen.add(reverse(f"{provider}_callback"))
                self.assertEqual(len(seen), 1, f"{provider} has more than one callback: {seen}")

    def test_the_language_free_address_resolves_to_the_callback(self):
        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                match = resolve(f"/accounts/{provider}/login/callback/")
                self.assertEqual(match.view_name, f"{provider}_callback")

    def test_the_prefixed_address_still_resolves(self):
        """Confirmation links already sitting in inboxes point at the prefixed path; it must live.

        Resolved with that language active, because that is what a real request does: the locale
        middleware reads the prefix and activates it before anything reaches the URL resolver.
        """
        for code in LANGUAGES:
            with self.subTest(language=code):
                with translation.override(code):
                    match = resolve(f"/{code}/accounts/google/login/callback/")
                self.assertEqual(match.view_name, "google_callback")

    def test_the_reader_facing_account_pages_keep_their_language_prefix(self):
        """Only the callback is language-free. Everything a reader reads still names its language."""
        for code in LANGUAGES:
            with self.subTest(language=code):
                with translation.override(code):
                    self.assertTrue(reverse("account_login").startswith(f"/{code}/"))
                    self.assertTrue(reverse("account_profile").startswith(f"/{code}/"))


@override_settings(SOCIALACCOUNT_PROVIDERS=FAKE_APPS)
class AddressSentToTheProviderTests(TestCase):
    """What actually leaves the site, rather than what reverse() says on its own."""

    def _redirect_uri(self, provider, language):
        response = self.client.post(f"/{language}/accounts/{provider}/login/", {"process": "login"})
        self.assertIn(response.status_code, (301, 302), f"{provider}/{language} did not redirect")
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(response["Location"]).query)
        self.assertIn("redirect_uri", query, f"no redirect_uri for {provider}/{language}")
        return query["redirect_uri"][0]

    def test_the_address_sent_to_the_provider_carries_no_language(self):
        for provider in PROVIDERS:
            for code in LANGUAGES:
                with self.subTest(provider=provider, language=code):
                    uri = self._redirect_uri(provider, code)
                    self.assertEqual(urllib.parse.urlsplit(uri).path, f"/accounts/{provider}/login/callback/")

    def test_signing_in_from_different_languages_sends_one_and_the_same_address(self):
        """This is the bug itself: three languages used to mean three unregistered addresses."""
        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                sent = {self._redirect_uri(provider, code) for code in LANGUAGES}
                self.assertEqual(len(sent), 1, f"{provider} still sends {sent}")
