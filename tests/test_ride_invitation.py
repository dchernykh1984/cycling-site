"""The invitation a virtual ride takes to Strava and intervals.icu: the rider's language, the page in it."""

from django.test import TestCase, override_settings
from django.utils import translation
from django.utils.translation import gettext
from wagtail.models import Site

from accounts.models import User
from trainer.invitation import club_name, invitation

NAMED = {"SITE_BASE_URL": "https://ride.test/", "ORGANIZATION_SHORT_NAME": "UBT", "ORGANIZATION_NAME": "Big Club"}


def _words(language: str, club: str) -> str:
    with translation.override(language):
        return gettext("Ride with %(club)s!") % {"club": club}


@override_settings(**NAMED)
class InvitationTests(TestCase):
    def test_the_rider_s_own_language_names_the_words_and_the_page(self):
        for language in ("ru", "kk", "en"):
            rider = User(username=language, preferred_language=language)
            with translation.override("en" if language != "en" else "ru"):  # whatever the request came in
                text = invitation(rider)
            self.assertEqual(text, f"{_words(language, 'UBT')}\nhttps://ride.test/{language}/virtual-ride/")

    def test_without_a_choice_the_language_of_the_request_decides(self):
        with translation.override("kk"):
            text = invitation(User(username="anna"))
        self.assertEqual(text, f"{_words('kk', 'UBT')}\nhttps://ride.test/kk/virtual-ride/")

    def test_each_language_has_its_own_words(self):
        self.assertEqual(len({_words(language, "UBT") for language in ("ru", "kk", "en")}), 3)

    def test_the_club_is_the_short_name_then_the_full_one_then_the_site_s(self):
        self.assertEqual(club_name(), "UBT")
        with override_settings(ORGANIZATION_SHORT_NAME=""):
            self.assertEqual(club_name(), "Big Club")
        Site.objects.filter(is_default_site=True).update(site_name="Cycling")
        with override_settings(ORGANIZATION_SHORT_NAME="", ORGANIZATION_NAME=""):
            self.assertEqual(club_name(), "Cycling")
            Site.objects.update(site_name="")
            with translation.override("en"):
                self.assertEqual(invitation(User(username="anna")), "https://ride.test/en/virtual-ride/")
