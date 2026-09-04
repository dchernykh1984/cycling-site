"""The controls around the calendar grid.

FullCalendar draws its own toolbar and labels the buttons from its own bundle -- which spells
`today` in lower case and carries no Kazakh at all. The labels a reader sees have to come from
our catalogue instead, and the test asserts against `gettext`, never against a pasted word.
"""

from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from tests.language_urls import in_language


class TodayButtonTests(TestCase):
    def test_the_label_is_translated_in_every_locale(self):
        for language in ("ru", "kk", "en"):
            with self.subTest(language=language):
                with translation.override(language):
                    expected = translation.gettext("Today")
                response = self.client.get(in_language(reverse("calendar"), language))
                self.assertContains(response, f"buttonText: {{ today: '{expected}' }}")

    def test_the_label_starts_with_a_capital_letter(self):
        for language in ("ru", "kk", "en"):
            with self.subTest(language=language), translation.override(language):
                label = translation.gettext("Today")
                self.assertEqual(label[:1], label[:1].upper())

    def test_the_russian_and_kazakh_labels_are_not_the_english_source(self):
        """A missing or fuzzy catalogue entry silently serves the English string."""
        for language in ("ru", "kk"):
            with self.subTest(language=language), translation.override(language):
                self.assertNotEqual(translation.gettext("Today"), "Today")
