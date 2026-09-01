"""Copying an event that happens again.

A club's monthly time trial and a race that returns every August differ from last year's only in
the dates. Cloning fills the submit form from an existing event so the organizer sets the dates and
saves, instead of retyping the description, the categories and the registration settings.
"""

import datetime
import json

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from calendar_app.models import Competition, Discipline, DisciplineCategory, EventType
from registrations.models import RegistrationCategory
from tests.language_urls import in_language

TODAY = datetime.date.today()


class CloneTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organizer = User.objects.create_user(
            username="organizer", email="o@example.com", password="Pass1234!", role=User.Role.ORGANIZER
        )
        cls.stranger = User.objects.create_user(
            username="stranger", email="s@example.com", password="Pass1234!", role=User.Role.PARTICIPANT
        )
        category = DisciplineCategory.objects.create(name_ru="Road", name_en="Road", order=1)
        cls.discipline = Discipline.objects.create(name_ru="ITT", name_en="ITT", category=category, order=1)
        cls.event_type = EventType.objects.create(name_ru="Race", order=1)
        cls.source = Competition.objects.create(
            title_ru="Birthday time trial",
            title_en="Birthday time trial",
            description_ru="<p>Two laps, individual start.</p>",
            date_start=TODAY - datetime.timedelta(days=30),
            date_end=TODAY - datetime.timedelta(days=29),
            status=Competition.Status.APPROVED,
            submitted_by=cls.organizer,
            url_announcement="https://example.kz/announcement",
            url_results="https://example.kz/results-2025",
            registration_enabled=True,
            birth_date_mode="year",
            additional_info_label="Bike type",
            max_participants=120,
        )
        cls.source.event_types.set([cls.event_type])
        cls.source.disciplines.set([cls.discipline])
        RegistrationCategory.objects.create(
            competition=cls.source,
            name="Women 2011-1991",
            female=True,
            birth_from=datetime.date(1991, 1, 1),
            birth_to=datetime.date(2011, 12, 31),
            laps=2,
        )

    def _clone_page(self, user=None):
        self.client.force_login(user or self.organizer)
        url = in_language(reverse("calendar_submit"), "en") + f"?clone={self.source.pk}"
        return self.client.get(url)

    def test_the_form_arrives_filled_in(self):
        form = self._clone_page().context["form"]
        self.assertEqual(form.initial["title_ru"], "Birthday time trial")
        self.assertEqual(form.initial["description_ru"], "<p>Two laps, individual start.</p>")
        self.assertEqual(form.initial["url_announcement"], "https://example.kz/announcement")
        self.assertEqual(form.initial["event_types"], [self.event_type.pk])
        self.assertEqual(form.initial["disciplines"], [self.discipline.pk])

    def test_the_dates_are_left_for_the_organizer(self):
        """The one thing that is never the same as last time."""
        form = self._clone_page().context["form"]
        self.assertNotIn("date_start", form.initial)
        self.assertNotIn("date_end", form.initial)

    def test_last_years_results_are_not_carried_over(self):
        self.assertNotIn("url_results", self._clone_page().context["form"].initial)

    def test_the_registration_settings_come_along(self):
        reg_form = self._clone_page().context["reg_form"]
        self.assertTrue(reg_form.initial["registration_enabled"])
        self.assertEqual(reg_form.initial["birth_date_mode"], "year")
        self.assertEqual(reg_form.initial["max_participants"], 120)
        self.assertEqual(reg_form.initial["additional_info_label"], "Bike type")

    def test_the_categories_come_along(self):
        categories = json.loads(self._clone_page().context["categories_json"])
        self.assertEqual(len(categories), 1)
        self.assertEqual(categories[0]["name"], "Women 2011-1991")
        self.assertEqual(categories[0]["birth_from"], "1991")  # a year, as this event counts them
        self.assertTrue(categories[0]["female"])

    def test_the_page_says_what_it_copied(self):
        self.assertContains(self._clone_page(), "Birthday time trial")

    def test_an_ordinary_submit_page_is_untouched(self):
        self.client.force_login(self.organizer)
        response = self.client.get(in_language(reverse("calendar_submit"), "en"))
        self.assertEqual(response.context["categories_json"], "[]")
        self.assertIsNone(response.context["clone_source"])
        self.assertEqual(response.context["form"].initial, {})

    def test_only_somebody_who_may_edit_the_event_may_copy_it(self):
        """Its description and its categories are as much its content as its title."""
        self.assertEqual(self._clone_page(self.stranger).status_code, 403)

    def test_a_deleted_event_cannot_be_copied(self):
        self.source.is_deleted = True
        self.source.save(update_fields=["is_deleted"])
        self.assertEqual(self._clone_page().status_code, 404)

    def test_nonsense_in_the_query_is_ignored_rather_than_crashing(self):
        self.client.force_login(self.organizer)
        response = self.client.get(in_language(reverse("calendar_submit"), "en") + "?clone=not-a-number")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["clone_source"])

    def test_a_missing_event_is_a_404(self):
        self.client.force_login(self.organizer)
        response = self.client.get(in_language(reverse("calendar_submit"), "en") + "?clone=999999")
        self.assertEqual(response.status_code, 404)


class CloneButtonTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organizer = User.objects.create_user(
            username="button_organizer", email="b@example.com", password="Pass1234!", role=User.Role.ORGANIZER
        )
        cls.competition = Competition.objects.create(
            title_ru="Race",
            date_start=TODAY + datetime.timedelta(days=5),
            status=Competition.Status.APPROVED,
            submitted_by=cls.organizer,
        )

    def _detail(self, user=None):
        if user:
            self.client.force_login(user)
        return self.client.get(in_language(reverse("competition_detail", args=[self.competition.pk]), "en"))

    def test_whoever_may_edit_sees_the_button(self):
        self.assertContains(self._detail(self.organizer), f"?clone={self.competition.pk}")

    def test_a_reader_does_not(self):
        self.assertNotContains(self._detail(), f"?clone={self.competition.pk}")
