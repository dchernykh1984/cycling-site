"""A draft another page hands the event form: the virtual ride's "Add event" fills the form, nothing more.

The page posts the event's words in each language, its date and its types and disciplines named in English; the
form opens filled with them for the member to check and submit. Nothing is an event until they do.
"""

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from calendar_app.models import Competition, Discipline, EventType
from calendar_app.views import _selected_discipline_ids

DRAFT = {
    "title_ru": "Virtual group race: Old centre",
    "title_kk": "Virtual group race (kk)",
    "title_en": "Virtual group race: Old centre",
    "preview_text_en": "Virtual race Old centre: Tuesday, 2 December, 19:00 (UTC+5)",
    "description_en": '<p>Start at 19:00.</p><script>alert(1)</script><p><a href="https://example.com/">join</a></p>',
    "date_start": "2026-12-02",
    "event_type": ["Virtual Ride", "No such type"],
    "discipline": ["Coffee Ride"],
}


class EventDraftTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.member = User.objects.create_user(
            username="rider", email="r@example.com", password="Pass1234!", role=User.Role.PARTICIPANT
        )
        # the lists as the migrations seed them, which every database has
        cls.coffee = Discipline.objects.get(name_en="Coffee Ride")

    def setUp(self):
        self.client.force_login(self.member)

    def test_the_virtual_ride_is_a_type_of_event_in_every_language(self):
        virtual = EventType.objects.get(name_en="Virtual Ride")
        self.assertTrue(virtual.name_ru and virtual.name_kk)
        # after the types that were there before it, not ahead of the plain race
        self.assertGreater(virtual.order, EventType.objects.get(name_en="Professional Race").order)

    def test_a_draft_opens_the_form_filled_with_it(self):
        response = self.client.post(reverse("calendar_submit_draft"), DRAFT)
        self.assertRedirects(response, reverse("calendar_submit") + "?draft=1")
        form = self.client.get(response["Location"]).context["form"]
        self.assertEqual(form.initial["title_en"], DRAFT["title_en"])
        self.assertEqual(form.initial["preview_text_en"], DRAFT["preview_text_en"])
        self.assertEqual(form.initial["date_start"], "2026-12-02")
        # types and disciplines by their English names, as every database names them; an unknown name is no type
        self.assertEqual(form.initial["event_types"], [EventType.objects.get(name_en="Virtual Ride").pk])
        self.assertEqual(_selected_discipline_ids(form), [self.coffee.pk])

    def test_a_draft_s_description_is_cleaned_as_an_event_s_is(self):
        self.client.post(reverse("calendar_submit_draft"), DRAFT)
        description = self.client.get(reverse("calendar_submit") + "?draft=1").context["form"].initial["description_en"]
        self.assertNotIn("<script", description)
        self.assertIn('href="https://example.com/"', description)

    def test_the_form_is_empty_unless_its_address_asks_for_the_draft(self):
        self.client.post(reverse("calendar_submit_draft"), DRAFT)
        self.assertNotIn("title_en", self.client.get(reverse("calendar_submit")).context["form"].initial)

    def test_a_date_no_calendar_has_is_left_for_the_form_to_ask(self):
        self.client.post(reverse("calendar_submit_draft"), {**DRAFT, "date_start": "2026-02-30"})
        self.assertNotIn("date_start", self.client.get(reverse("calendar_submit") + "?draft=1").context["form"].initial)

    def test_nothing_is_an_event_until_it_is_submitted_and_then_the_draft_is_gone(self):
        self.client.post(reverse("calendar_submit_draft"), DRAFT)
        self.assertFalse(Competition.objects.exists())
        self.client.post(reverse("calendar_submit"), {"title_ru": "Virtual race", "date_start": "2026-12-02"})
        self.assertTrue(Competition.objects.filter(title_ru="Virtual race").exists())
        self.assertNotIn("title_en", self.client.get(reverse("calendar_submit") + "?draft=1").context["form"].initial)

    def test_a_reader_who_is_not_signed_in_is_asked_to_sign_in(self):
        self.client.logout()
        response = self.client.post(reverse("calendar_submit_draft"), DRAFT)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("account_login"), response["Location"])
