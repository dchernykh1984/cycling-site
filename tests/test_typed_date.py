"""A date typed as DD.MM.YYYY with the calendar beside it (cycling_site/typed_date.py): what the server takes, in
the profile's own date of birth and a person's without an account, and the words it refuses in."""

import datetime
import re

from django import forms
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone, translation

from accounts import virtual_members
from accounts.models import User, VirtualMember
from cycling_site.typed_date import FORMAT_ERROR, TypedDateField, TypedDateInput
from tests.language_urls import in_language

MARCH_5 = datetime.date(2012, 3, 5)


class TypedDateFieldTests(TestCase):
    def test_a_date_reads_as_typed_on_any_keyboard_and_as_iso(self):
        field = TypedDateField()
        for typed in (
            "05.03.2012",
            "5.3.2012",
            " 05.03.2012 ",
            "05/03/2012",
            "05-03-2012",
            "05 03 2012",
            "05,03,2012",
            "2012-03-05",
        ):
            self.assertEqual(field.clean(typed), MARCH_5, typed)

    def test_what_is_no_date_is_refused_in_words_that_say_how_to_type_it(self):
        field = TypedDateField()
        for typed in ("31.02.2012", "05.03.12", "2012", "05.13.2012", "5 March 2012", "05032012"):
            with self.assertRaises(forms.ValidationError) as caught:
                field.clean(typed)
            self.assertEqual(caught.exception.messages, [str(FORMAT_ERROR)], typed)

    def test_the_field_shows_its_date_as_typed_and_opens_the_calendar_from_1900_to_today(self):
        html = TypedDateInput().render("born", MARCH_5, {"id": "id_born"})
        self.assertRegex(html, r'<input type="text" name="born" value="05.03.2012"')
        self.assertIn('inputmode="numeric"', html)
        self.assertIn('autocomplete="off"', html)  # nobody's own birthday offered for another person
        self.assertIn(
            f'<input type="date" tabindex="-1" aria-hidden="true" min="1900-01-01" '
            f'max="{timezone.localdate():%Y-%m-%d}">',
            html,
        )
        with translation.override("ru"):
            html = TypedDateInput().render("born", None, {"id": "id_born"})
            self.assertIn(f'placeholder="{translation.gettext("DD.MM.YYYY")}"', html)
            self.assertIn(translation.pgettext("a button that opens a date picker", "Calendar"), html)
            self.assertIn(f'data-msg-format="{translation.gettext(FORMAT_ERROR)}"', html)


class ProfileBirthDateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="typed", email="typed@test.local", password="x-pass-123")
        self.client.force_login(self.user)

    def _save(self, born, lang="en"):
        return self.client.post(
            in_language(reverse("account_profile_edit"), lang),
            {"first_name": "Dana", "last_name": "Ivanova", "gender": "F", "birth_date": born},
        )

    def test_a_date_typed_with_dots_is_saved(self):
        self._save("05.03.2012")
        self.user.refresh_from_db()
        self.assertEqual(self.user.birth_date, MARCH_5)

    def test_a_date_that_cannot_be_read_comes_back_marked_with_the_reason_in_the_page_s_language(self):
        for lang in ("ru", "kk", "en"):
            page = self._save("31.02.2012", lang)
            self.assertEqual(page.status_code, 200, lang)
            html = page.content.decode()
            field = re.search(r'<input type="text" name="birth_date"[^>]*>', html).group(0)
            self.assertIn('aria-invalid="true"', field)
            self.assertIn("is-invalid", field)
            with translation.override(lang):
                self.assertIn(f'data-error-for="birth_date">{translation.gettext(FORMAT_ERROR)}<', html)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.birth_date)

    def test_a_date_in_the_future_is_refused_as_no_date_of_birth(self):
        page = self._save((timezone.localdate() + datetime.timedelta(days=1)).strftime("%d.%m.%Y"))
        self.assertEqual(page.status_code, 200)
        self.assertIn("between 1900 and today", page.content.decode())
        self.user.refresh_from_db()
        self.assertIsNone(self.user.birth_date)

    def test_the_member_s_own_date_may_be_filled_from_the_browser_s_autofill(self):
        page = self.client.get(in_language(reverse("account_profile_edit"), "en"))
        self.assertRegex(page.content.decode(), r'<input type="text" name="birth_date"[^>]*autocomplete="bday"')


class PersonBirthDateTests(TestCase):
    def setUp(self):
        self.coach = User.objects.create_user(
            username="coach", email="coach@test.local", password="x-pass-123", role=User.Role.ORGANIZER
        )
        virtual_members.consent(self.coach)
        self.client.force_login(self.coach)

    def test_a_person_s_date_typed_with_dots_is_saved_and_shown_so_when_edited(self):
        self.client.post(
            in_language(reverse("account_virtual_add"), "en"),
            {"last_name": "Ivanova", "first_name": "Dana", "gender": "F", "birth_date": "5.3.2012"},
        )
        person = VirtualMember.objects.get()
        self.assertEqual(person.birth_date, MARCH_5)
        page = self.client.get(in_language(reverse("account_virtual_edit", args=[person.pk]), "en"))
        self.assertRegex(page.content.decode(), r'<input type="text" name="birth_date" value="05.03.2012"')

    def test_the_card_s_span_of_dates_is_typed_as_well(self):
        VirtualMember.objects.create(
            owner=self.coach, last_name="Ivanova", first_name="Dana", gender="F", birth_date=MARCH_5
        )
        html = self.client.get(in_language(reverse("account_profile"), "en")).content.decode()
        for field in ("vm-born-from", "vm-born-to"):
            self.assertRegex(html, rf'<input type="text" name="born_\w+"[^>]*id="{field}"')
