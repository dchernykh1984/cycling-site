"""The sign-up page introduces the other ways in with a whole sentence, in every language."""

from django.test import TestCase
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext


class OtherWaysInTests(TestCase):
    def test_the_other_ways_in_are_introduced_by_a_whole_sentence_in_each_language(self):
        for language in ("ru", "kk", "en"):
            with self.subTest(language=language), translation.override(language):
                # allauth's own heading: half a sentence in Russian, English on the Kazakh page
                theirs = gettext("Or use a third-party")
                ours = gettext("Or sign in with another service")
                page = self.client.get(reverse("account_signup"))
                self.assertContains(page, ours)
                self.assertNotContains(page, theirs)
                if language != "en":
                    self.assertNotEqual(ours, "Or sign in with another service", "no translation")
