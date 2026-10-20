"""The month and weekday names the calendar script writes dates with (issue #330)."""

from django.test import SimpleTestCase
from django.utils.translation import override as translation_override

from calendar_app.views import calendar_date_words


class CalendarDateWordsTests(SimpleTestCase):
    def test_every_month_and_weekday_is_there(self):
        words = calendar_date_words()
        self.assertEqual(len(words["months"]), 12)
        self.assertEqual(len(words["weekdays"]), 7)

    def test_the_week_starts_on_monday(self):
        with translation_override("en"):
            words = calendar_date_words()
        self.assertEqual(words["weekdays"][0], "Monday")
        self.assertEqual(words["weekdays"][6], "Sunday")

    def test_months_take_the_form_a_date_takes(self):
        """Russian writes a date with the genitive month, which ends in 'ya' -- not the bare name."""
        # Built from its code point: source files stay ASCII (see the pre-commit hook).
        genitive_ending = "\u044f"
        with translation_override("ru"):
            october = calendar_date_words()["months"][9]
        self.assertTrue(october.endswith(genitive_ending), october)

    def test_kazakh_comes_from_the_catalogue_not_the_browser(self):
        with translation_override("kk"):
            words = calendar_date_words()
        with translation_override("en"):
            english = calendar_date_words()
        self.assertNotEqual(words["months"], english["months"])
        self.assertNotEqual(words["weekdays"], english["weekdays"])

    def test_inside_a_date_russian_and_kazakh_write_lower_case(self):
        for language in ("ru", "kk"):
            with translation_override(language):
                words = calendar_date_words()
            for word in words["months"] + words["weekdays"]:
                self.assertEqual(word, word.lower(), (language, word))

    def test_english_keeps_its_capitals(self):
        with translation_override("en"):
            words = calendar_date_words()
        self.assertEqual(words["months"][9], "October")
        self.assertEqual(words["weekdays"][1], "Tuesday")
