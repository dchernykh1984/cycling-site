"""What the additional-info field is called.

Organizers collect very different things in that one field -- a bike type, a transfer preference,
a shirt size -- and "Additional info" tells the rider none of it. The label is now theirs to write.
"""

import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from accounts.models import User
from calendar_app.models import Competition
from registrations.forms import RegistrationForm
from tests.language_urls import in_language

TODAY = datetime.date.today()


def _competition(**kwargs):
    defaults = {
        "title_ru": "Race",
        "date_start": TODAY + datetime.timedelta(days=10),
        "status": Competition.Status.APPROVED,
        "registration_enabled": True,
        "birth_date_mode": "year",
    }
    defaults.update(kwargs)
    return Competition.objects.create(**defaults)


class LabelOnTheModelTests(TestCase):
    def test_the_organizers_wording_wins(self):
        competition = _competition(additional_info_label="Bike type")
        self.assertEqual(competition.additional_info_field_label, "Bike type")

    def test_without_one_the_field_keeps_its_built_in_name(self):
        competition = _competition()
        with translation.override("en"):
            self.assertEqual(competition.additional_info_field_label, "Additional info")

    def test_a_strava_field_says_so_when_nothing_was_written(self):
        competition = _competition(additional_info_mode=Competition.AdditionalInfoMode.STRAVA)
        with translation.override("en"):
            self.assertEqual(competition.additional_info_field_label, "Strava link")

    def test_a_wording_of_spaces_is_not_a_wording(self):
        competition = _competition(additional_info_label="   ")
        with translation.override("en"):
            self.assertEqual(competition.additional_info_field_label, "Additional info")

    def test_the_built_in_name_follows_the_readers_language(self):
        competition = _competition()
        with translation.override("ru"):
            russian = competition.additional_info_field_label
        with translation.override("en"):
            english = competition.additional_info_field_label
        self.assertNotEqual(russian, english)

    def test_a_written_wording_is_the_same_in_every_language(self):
        """One string, deliberately: the organizer writes what they say to their own riders."""
        competition = _competition(additional_info_label="Transfer preference")
        for locale in ("ru", "kk", "en"):
            with translation.override(locale):
                self.assertEqual(competition.additional_info_field_label, "Transfer preference")


class LabelOnTheRegistrationFormTests(TestCase):
    def test_the_form_field_carries_it(self):
        competition = _competition(additional_info_label="Bike type")
        form = RegistrationForm(competition=competition)
        self.assertEqual(form.fields["additional_info"].label, "Bike type")

    def test_the_field_is_still_plain_text(self):
        """Renaming it does not change what it collects."""
        competition = _competition(additional_info_label="Bike type")
        form = RegistrationForm(competition=competition)
        self.assertEqual(form.fields["additional_info"].max_length, 100)
        self.assertFalse(form.fields["additional_info"].required)

    def test_a_hidden_field_has_no_label_to_carry(self):
        competition = _competition(
            additional_info_mode=Competition.AdditionalInfoMode.NONE, additional_info_label="Bike type"
        )
        self.assertNotIn("additional_info", RegistrationForm(competition=competition).fields)


class LabelOnThePageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = _competition(additional_info_label="Bike type")
        cls.rider = User.objects.create_user(
            username="rider", email="rider@example.com", password="Pass1234!", role=User.Role.PARTICIPANT
        )

    def test_the_registration_page_asks_for_it_by_that_name(self):
        self.client.force_login(self.rider)
        url = in_language(reverse("registrations:register", args=[self.competition.pk]), "en")
        self.assertContains(self.client.get(url), "Bike type")

    def test_the_participant_list_heads_its_column_with_it(self):
        """The table is only drawn once somebody has entered, so the list needs one rider."""
        from registrations.models import CompetitionRegistration

        CompetitionRegistration.objects.create(
            competition=self.competition,
            user=self.rider,
            first_name="Alisa",
            last_name="Troitskaya",
            gender="F",
            birth_date=datetime.date(1995, 5, 1),
            additional_info="Gravel",
        )
        url = in_language(reverse("registrations:participant_list", args=[self.competition.pk]), "en")
        response = self.client.get(url)
        self.assertContains(response, "Bike type")
        self.assertNotContains(response, ">Info<")


class LabelInTheExportTests(TestCase):
    """The CSV is read by scripts as well as people, so its header does not follow the interface."""

    @classmethod
    def setUpTestData(cls):
        cls.organizer = User.objects.create_user(
            username="export_organizer", email="e@example.com", password="Pass1234!", role=User.Role.ORGANIZER
        )

    def _header(self, competition):
        self.client.force_login(self.organizer)
        url = in_language(reverse("registrations:export_csv", args=[competition.pk]), "ru")
        return self.client.get(url).content.decode("utf-8-sig").splitlines()[0]

    def test_the_organizers_wording_reaches_the_file(self):
        competition = _competition(submitted_by=self.organizer, additional_info_label="Bike type")
        self.assertIn("Bike type", self._header(competition))

    def test_without_one_the_header_stays_english_whatever_the_page_language(self):
        competition = _competition(submitted_by=self.organizer)
        header = self._header(competition)
        self.assertIn("Additional info", header)
        self.assertIn("First name", header)
