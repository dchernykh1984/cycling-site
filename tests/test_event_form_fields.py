"""The event form draws each of its own blocks once.

The submit and edit pages render most fields in one generic loop and give a few of them a block of
their own. A field with its own block has to be kept out of the loop, or the page shows it twice --
which is what happened to the link preview upload: two file pickers under two different labels.
"""

import datetime

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from calendar_app.models import Competition


class FormFieldsDrawnOnceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organizer = User.objects.create_user(
            username="org", email="org@example.com", password="pw", role=User.Role.ORGANIZER
        )
        cls.event = Competition.objects.create(
            title_ru="Race",
            date_start=datetime.date(2030, 1, 1),
            status=Competition.Status.APPROVED,
            submitted_by=cls.organizer,
        )

    def _pages(self):
        self.client.force_login(self.organizer)
        for name, url in (
            ("submit", reverse("calendar_submit")),
            ("edit", reverse("competition_edit", args=[self.event.pk])),
        ):
            yield name, self.client.get(url).content.decode()

    def test_the_preview_upload_appears_once(self):
        for name, html in self._pages():
            with self.subTest(page=name):
                self.assertEqual(html.count('name="preview_image"'), 1)
