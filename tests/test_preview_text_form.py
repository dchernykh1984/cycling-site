"""Writing the link preview line on the event form (issue #318).

An organizer types the line a chat shows under the title of a pasted link -- the meeting time and
place, which the generated summary cannot know -- once per language, next to the title.
"""

import datetime

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from calendar_app.models import Competition
from tests.language_urls import in_language

NEXT_WEEK = datetime.date.today() + datetime.timedelta(days=7)


class PreviewTextFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organizer = User.objects.create_user(
            username="organizer", email="o@example.com", password="Pass1234!", role=User.Role.ORGANIZER
        )

    def setUp(self):
        self.client.force_login(self.organizer)

    def _payload(self, **extra):
        payload = {"title_ru": "Saturday ride", "date_start": f"{NEXT_WEEK:%Y-%m-%d}"}
        payload.update(extra)
        return payload

    def _event(self, **fields):
        return Competition.objects.create(
            title_ru="Saturday ride",
            date_start=NEXT_WEEK,
            status=Competition.Status.APPROVED,
            submitted_by=self.organizer,
            **fields,
        )

    def test_every_language_tab_offers_the_field(self):
        page = self.client.get(reverse("calendar_submit"))
        for language in ("ru", "kk", "en"):
            with self.subTest(language=language):
                self.assertContains(page, f'name="preview_text_{language}"')

    def test_a_new_event_keeps_what_was_typed(self):
        self.client.post(
            reverse("calendar_submit"),
            self._payload(preview_text_ru="Meet 6:15", preview_text_kk="Meet 6:15 kk", preview_text_en="Meet 6:15 en"),
        )
        event = Competition.objects.get(title_ru="Saturday ride")
        self.assertEqual(
            (event.preview_text_ru, event.preview_text_kk, event.preview_text_en),
            ("Meet 6:15", "Meet 6:15 kk", "Meet 6:15 en"),
        )

    def test_an_edit_changes_it_and_can_clear_it(self):
        event = self._event(preview_text_ru="Meet 6:15", preview_text_en="Meet 6:15 en")
        self.client.post(
            reverse("competition_edit", args=[event.pk]),
            self._payload(title_ru="Saturday ride edited", preview_text_ru="Meet 7:00"),
        )
        event.refresh_from_db()
        self.assertEqual(event.title_ru, "Saturday ride edited", "the edit was refused")
        self.assertEqual(event.preview_text_ru, "Meet 7:00")
        self.assertEqual(event.preview_text_en, "")

    def test_the_edit_form_shows_the_current_line(self):
        event = self._event(preview_text_ru="Meet 6:15")
        form = self.client.get(reverse("competition_edit", args=[event.pk])).context["form"]
        self.assertEqual(form.initial["preview_text_ru"], "Meet 6:15")

    def test_a_clone_keeps_the_meeting_point(self):
        """A weekly ride meets at the same place every week."""
        event = self._event(preview_text_ru="Meet 6:15 at the bike shop")
        url = in_language(reverse("calendar_submit"), "en") + f"?clone={event.pk}"
        form = self.client.get(url).context["form"]
        self.assertEqual(form.initial["preview_text_ru"], "Meet 6:15 at the bike shop")

    def test_a_line_longer_than_the_column_is_refused(self):
        limit = Competition._meta.get_field("preview_text").max_length
        response = self.client.post(reverse("calendar_submit"), self._payload(preview_text_ru="x" * (limit + 1)))
        self.assertTrue(response.context["form"].errors["preview_text_ru"])
        self.assertFalse(Competition.objects.filter(title_ru="Saturday ride").exists())
