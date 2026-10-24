"""A skin offered once (settings.SKIN_OFFER): asked of readers in another skin until they try it."""

from django.test import TestCase, override_settings

from accounts.models import User
from cycling_site.skins import OFFER_COOKIE

OFFER = 'id="skin-offer"'


@override_settings(SKIN_OFFER="orange")
class SkinOfferTests(TestCase):
    def _member(self, theme):
        user = User.objects.create_user(username=f"{theme}@example.com", email=f"{theme}@example.com", password="x")
        user.theme = theme
        user.save(update_fields=["theme"])
        self.client.force_login(user)
        return user

    def _page(self):
        return self.client.get("/ru/news/")

    def test_a_member_in_another_skin_is_asked_once_and_not_after_trying_it(self):
        user = self._member("dark")
        self.assertContains(self._page(), OFFER)
        user.theme = "orange"
        user.save(update_fields=["theme"])
        self.assertNotContains(self._page(), OFFER)
        user.refresh_from_db()
        self.assertEqual(user.tried_skins, ["orange"])
        self.assertEqual(user.dismissed_hints, [])  # the setup hints' list stays theirs
        # Back in dark: tried once, never asked again.
        user.theme = "dark"
        user.save(update_fields=["theme"])
        self.assertNotContains(self._page(), OFFER)

    def test_a_member_already_in_the_skin_is_not_asked(self):
        self._member("orange")
        self.assertNotContains(self._page(), OFFER)

    def test_a_guest_in_another_skin_is_asked_until_a_page_is_drawn_in_it(self):
        self.client.cookies["skin"] = "light"
        response = self._page()
        self.assertContains(response, OFFER)
        self.assertNotIn(OFFER_COOKIE, response.cookies)
        self.client.cookies["skin"] = "orange"
        response = self._page()
        self.assertNotContains(response, OFFER)
        self.assertEqual(response.cookies[OFFER_COOKIE].value, "orange")
        self.client.cookies["skin"] = "light"
        self.assertNotContains(self._page(), OFFER)

    def test_a_first_visit_opens_in_the_skin_on_offer_and_is_never_asked(self):
        response = self._page()
        self.assertNotContains(response, OFFER)
        self.assertEqual(response.cookies[OFFER_COOKIE].value, "orange")

    @override_settings(SKIN_OFFER="")
    def test_nothing_on_offer_asks_nothing(self):
        self._member("dark")
        self.assertNotContains(self._page(), OFFER)

    @override_settings(SKIN_OFFER="no-such-skin")
    def test_an_offer_of_a_skin_that_is_gone_asks_nothing(self):
        self._member("dark")
        self.assertNotContains(self._page(), OFFER)

    def test_a_guest_gets_the_cookie_on_pages_only_not_on_the_api_or_files(self):
        response = self.client.get("/api/v1/news/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(OFFER_COOKIE, response.cookies)
        self.assertNotIn(OFFER_COOKIE, self.client.get("/robots.txt").cookies)

    def test_a_form_post_or_a_json_call_writes_nothing(self):
        user = self._member("orange")
        self.client.post("/ru/accounts/theme/", data="{}", content_type="application/json")
        user.refresh_from_db()
        self.assertEqual(user.tried_skins, [])
