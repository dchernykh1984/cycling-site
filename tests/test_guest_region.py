"""A guest's calendar, list and map open on their own region (#332).

The places are made up and lie in the South Atlantic: the test database carries the seeded real
geography, and none of it is within reach of these points.
"""

import datetime

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from calendar_app.guest_region import OFFERED_COOKIE
from calendar_app.models import Competition
from locations.models import add_location_child
from tests.language_urls import in_language

BROWSER = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
NEAR_NORTHVILLE = (-40.02, -20.02)


def _visitor(lat, lng, agent=BROWSER):
    return {"HTTP_CF_IPLATITUDE": str(lat), "HTTP_CF_IPLONGITUDE": str(lng), "HTTP_USER_AGENT": agent}


def _event(venue, days):
    return Competition.objects.create(
        title_ru="Race",
        date_start=datetime.date.today() + datetime.timedelta(days=days),
        status=Competition.Status.APPROVED,
        location=venue,
    )


class GuestRegionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        country = add_location_child(None, name="Testland", name_ru="Testland")
        cls.north = add_location_child(country, name="North", name_ru="North", lat="-38.0", lng="-18.0")
        northville = add_location_child(cls.north, name="Northville", name_ru="Northville", lat="-40.0", lng="-20.0")
        _event(add_location_child(northville, name="Square", name_ru="Square"), days=5)
        # A large region whose centre lies nearer the visitor than its only city does.
        cls.vast = add_location_child(country, name="Vast", name_ru="Vast", lat="-40.03", lng="-20.03")
        faraway = add_location_child(cls.vast, name="Faraway", name_ru="Faraway", lat="-41.0", lng="-21.5")
        _event(add_location_child(faraway, name="Field", name_ru="Field"), days=5)

    def _open(self, name="calendar_list", **headers):
        return self.client.get(in_language(reverse(name), "ru"), **headers)

    def test_a_guest_opens_on_the_region_of_the_city_nearest_to_them(self):
        """Not the region whose centre is nearest: a large region's centre can be nearer than a city."""
        for name in ("calendar", "calendar_list", "calendar_map"):
            with self.subTest(page=name):
                self.client.cookies.clear()
                response = self._open(name, **_visitor(*NEAR_NORTHVILLE))
                path = in_language(reverse(name), "ru")
                self.assertRedirects(response, f"{path}?location={self.north.pk}", fetch_redirect_response=False)
                self.assertEqual(response.cookies[OFFERED_COOKIE].value, "1")
                self.assertEqual(response.cookies[OFFERED_COOKIE]["max-age"], "")  # gone with the browser
                self.assertIn("no-store", response["Cache-Control"])
                self.assertIn("private", response["Cache-Control"])

    def test_a_guest_who_was_offered_their_region_keeps_what_they_chose_after_it(self):
        self.client.cookies[OFFERED_COOKIE] = "1"
        self.assertEqual(self._open(**_visitor(*NEAR_NORTHVILLE)).status_code, 200)

    def test_crawlers_and_link_previews_read_the_whole_calendar(self):
        for agent in (
            "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
            "Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)",
            "TelegramBot (like TwitterBot)",
            "WhatsApp/2.23.20.0 A",
            "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
            "",
        ):
            with self.subTest(agent=agent):
                self.assertEqual(self._open(**_visitor(*NEAR_NORTHVILLE, agent=agent)).status_code, 200)

    def test_without_a_point_or_far_from_every_city_the_calendar_stays_whole(self):
        self.assertEqual(self._open(HTTP_USER_AGENT=BROWSER).status_code, 200)
        self.assertEqual(self._open(**_visitor(-10.0, -30.0)).status_code, 200)
        self.assertEqual(self._open(**_visitor("nan", "x")).status_code, 200)

    def test_a_region_with_nothing_still_to_come_is_not_offered(self):
        Competition.objects.filter(location__path__startswith=self.north.path).update(
            date_start=datetime.date.today() - datetime.timedelta(days=30)
        )
        self.assertEqual(self._open(**_visitor(*NEAR_NORTHVILLE)).status_code, 200)

    def test_a_member_opens_on_their_own_preferences_not_on_a_region(self):
        member = User.objects.create_user(username="member", email="m@example.com", password="x-pass-123")
        self.client.force_login(member)
        self.assertEqual(self._open(**_visitor(*NEAR_NORTHVILLE)).status_code, 200)

    def test_an_address_that_already_says_what_to_show_is_shown_as_it_is(self):
        url = f"{in_language(reverse('calendar_list'), 'ru')}?date_from=2026-01-01"
        self.assertEqual(self.client.get(url, **_visitor(*NEAR_NORTHVILLE)).status_code, 200)


class PrivacyPolicyRegionTests(TestCase):
    def test_the_policy_says_how_the_region_is_found_and_that_nothing_is_kept(self):
        from django.utils import translation

        for language in ("ru", "kk", "en"):
            with self.subTest(language=language), translation.override(language):
                body = self.client.get(in_language(reverse("privacy_policy"), language)).content.decode()
                paragraph = translation.gettext(
                    "<strong>Your region.</strong> If you are not signed in, the calendar, the list and the map"
                    " open on the events of your region, when it can be told. The network provider that delivers"
                    " the site works out an approximate location from your IP address and passes it to us with the"
                    " request; we use it only to choose your region as the page opens and do not store it. A cookie"
                    " that lasts until you close the browser remembers that the region was offered, so that once"
                    " you clear it you keep the whole calendar."
                )
                self.assertIn(paragraph, body)
