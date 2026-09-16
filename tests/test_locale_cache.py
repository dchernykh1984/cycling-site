"""The redirect that picks a language must not be remembered by a browser.

An address without a language of its own answers differently to every reader: "/" sends one person
to /ru/ and the next to /en/, off their cookie, their stored preference and their Accept-Language.
It used to carry no cache directive at all, which leaves a browser free to store it -- and Safari
keeps redirects while honouring "Vary: Cookie" only in part, so an iPhone sent to /en/ once kept
sending itself there after the reader had chosen Russian, until the cache was cleared by hand.
"""

from django.test import Client, TestCase

EN_PHONE = "en-US,en;q=0.9"


class LanguageRedirectCacheTests(TestCase):
    def test_the_redirect_that_picks_a_language_is_never_stored(self):
        response = Client(HTTP_ACCEPT_LANGUAGE=EN_PHONE).get("/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/en/")
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_it_holds_for_a_deeper_address_too(self):
        response = Client(HTTP_ACCEPT_LANGUAGE=EN_PHONE).get("/calendar/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/en/calendar/")
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_a_page_that_names_its_own_language_is_left_cacheable(self):
        """/en/ answers the same to everyone who asks for it, so it keeps whatever caching it had."""
        response = Client(HTTP_ACCEPT_LANGUAGE=EN_PHONE).get("/en/calendar/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("no-store", response.get("Cache-Control", ""))

    def test_a_machine_facing_address_is_not_touched(self):
        """The API is the same in every language and never gets the language redirect at all."""
        response = Client().get("/api/v1/competitions/999999")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("no-store", response.get("Cache-Control", ""))

    def test_a_redirect_that_is_not_about_language_is_left_alone(self):
        """Only the chooser is marked. A guest sent to the login page is an ordinary redirect from
        an address that already names its language, and none of this middleware's business."""
        response = Client(HTTP_ACCEPT_LANGUAGE=EN_PHONE).get("/en/accounts/profile/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])
        self.assertNotIn("no-store", response.get("Cache-Control", ""))
