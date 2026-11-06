"""An event's additional field that collects the date of birth in full, from the person's account: a
member's, or a person's without one (issue #438) -- for an event that asks only the year of birth."""

import datetime
import re

from django.test import TestCase
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext

from accounts import virtual_members
from accounts.models import User, VirtualMember
from registrations.forms import EditRegistrationForm, RegistrationForm
from registrations.models import CompetitionRegistration
from registrations.tests import make_category, make_open_competition, make_registration, make_user
from tests.test_virtual_members import _bearer

BORN = datetime.date(1990, 4, 17)


def _field(html: str) -> str:
    """The additional field's input as the page draws it."""
    found = re.search(r'<input[^>]*name="[^"]*additional_info"[^>]*>', html)
    return found.group(0) if found else ""


class BirthDateModeTests(TestCase):
    def setUp(self):
        self.member = make_user("rider", first_name="Ivan", last_name="Petrov", gender="M", birth_date=BORN)
        self.client.force_login(self.member)

    def _event(self, mode="self_only"):
        comp = make_open_competition(registration_mode=mode, additional_info_mode="birth_date")
        make_category(comp)
        return comp

    def _url(self, comp):
        with translation.override("en"):
            return reverse("registrations:register", args=[comp.pk])

    def test_the_organizer_offers_it_beside_the_strava_link(self):
        organizer = make_user("org", role=User.Role.ORGANIZER)
        self.client.force_login(organizer)
        with translation.override("en"):
            page = self.client.get(reverse("calendar_submit"))
        self.assertContains(page, '<option value="birth_date" >Date of birth</option>', html=True)

    def test_the_field_is_named_after_it_and_a_date_filled_in_from_the_account(self):
        comp = self._event()
        with translation.override("en"):
            self.assertEqual(str(RegistrationForm(competition=comp).fields["additional_info"].label), "Date of birth")
        field = _field(self.client.get(self._url(comp)).content.decode())
        self.assertIn('type="date"', field)
        self.assertIn(f'value="{BORN.isoformat()}"', field)
        self.assertIn("readonly", field)

    def test_the_participant_list_heads_its_column_with_the_date_of_birth(self):
        comp = self._event()
        make_registration(comp, user=self.member, additional_info=BORN.isoformat())
        with translation.override("en"):
            page = self.client.get(reverse("registrations:participant_list", args=[comp.pk]))
        self.assertContains(page, "<th>Date of birth</th>", html=True)

    def test_an_event_taking_only_ones_own_data_keeps_the_accounts_date_whatever_the_form_says(self):
        comp = self._event()
        cat = comp.registration_categories.get()
        self.client.post(
            self._url(comp),
            {
                "first_name": "X",
                "last_name": "Y",
                "gender": "M",
                "birth_year": 1990,
                "category": cat.pk,
                "additional_info": "2001-01-01",
            },
        )
        self.assertEqual(CompetitionRegistration.objects.get().additional_info, BORN.isoformat())

    def test_where_anyone_may_be_entered_the_date_typed_is_kept_and_checked(self):
        comp = self._event(mode="free")
        cat = comp.registration_categories.get()
        data = {"first_name": "Oleg", "last_name": "Kim", "gender": "M", "birth_year": 1995, "category": cat.pk}
        refused = self.client.post(self._url(comp), {**data, "additional_info": "17.04.1995"})
        with translation.override("ru"):
            self.assertIn(gettext("Enter a valid date."), refused.context["form"].errors["additional_info"])
        future = self.client.post(self._url(comp), {**data, "additional_info": "2999-01-01"})
        self.assertIn("additional_info", future.context["form"].errors)
        self.client.post(self._url(comp), {**data, "additional_info": "1995-06-02"})
        self.assertEqual(CompetitionRegistration.objects.get().additional_info, "1995-06-02")

    def test_a_person_without_an_account_is_entered_with_their_own_date_on_the_page_and_through_the_api(self):
        virtual_members.consent(self.member)
        kid = VirtualMember.objects.create(
            owner=self.member, last_name="Sokolova", first_name="Dana", gender="F", birth_date=datetime.date(2012, 3, 4)
        )
        comp = self._event()
        cat = comp.registration_categories.get()
        rows = {row.key: row for row in self.client.get(self._url(comp)).context["rows"]}
        self.assertEqual(rows[f"v{kid.pk}"].form.initial["additional_info"], "2012-03-04")
        # what the folded form sends: the person's fields as filled in, and the date left empty
        sent = {"first_name": "Dana", "last_name": "Sokolova", "gender": "F", "birth_year": 2012, "category": cat.pk}
        self.client.post(
            self._url(comp),
            {
                "person": [f"v{kid.pk}"],
                **{f"pv{kid.pk}-{k}": v for k, v in sent.items()},
                f"pv{kid.pk}-additional_info": "",
            },
        )
        self.assertEqual(CompetitionRegistration.objects.get(virtual_member=kid).additional_info, "2012-03-04")
        CompetitionRegistration.objects.all().delete()
        answer = self.client.post(
            "/api/v1/registrations/",
            {"competition_id": comp.pk, "entries": [{"person": f"virtual:{kid.pk}"}]},
            content_type="application/json",
            **_bearer(self.member),
        )
        self.assertEqual(answer.json()[0]["errors"], {})
        self.assertEqual(CompetitionRegistration.objects.get().additional_info, "2012-03-04")

    def test_editing_ones_entry_leaves_the_accounts_date_where_the_event_takes_only_ones_own_data(self):
        comp = self._event()
        entry = make_registration(comp, user=self.member, additional_info=BORN.isoformat())
        form = EditRegistrationForm(
            {"city": "Taraz", "additional_info": "2001-01-01"},
            instance=entry,
            competition=comp,
            participant_fields_only=True,
        )
        self.assertTrue(form.fields["additional_info"].disabled)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["additional_info"], BORN.isoformat())


class OtherPagesTests(TestCase):
    """The organizer's page to add an entry and the page to edit one draw the form's own widgets: the
    date of birth is a date field there too, so a date is picked rather than typed in some format."""

    def setUp(self):
        self.organizer = make_user("org", role=User.Role.ORGANIZER)
        self.comp = make_open_competition(
            registration_mode="free", additional_info_mode="birth_date", submitted_by=self.organizer
        )
        make_category(self.comp)
        self.client.force_login(self.organizer)

    def test_the_organizer_adds_and_edits_the_date_in_a_date_field(self):
        with translation.override("en"):
            added = self.client.get(reverse("registrations:manual_add", args=[self.comp.pk]))
        self.assertIn('type="date"', _field(added.content.decode()))
        entry = make_registration(self.comp, user=self.organizer, additional_info="1990-04-17")
        with translation.override("en"):
            edited = self.client.get(reverse("registrations:edit_registration", args=[self.comp.pk, entry.pk]))
        field = _field(edited.content.decode())
        self.assertIn('type="date"', field)
        self.assertIn('value="1990-04-17"', field)
