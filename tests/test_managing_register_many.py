"""Registering oneself and the members one manages at once (issue #315, decisions 10, 16, 20, 22-26)."""

import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from accounts import managing
from accounts.models import User
from calendar_app.models import CompetitionInvite
from calendar_app.visibility import can_see
from registrations.models import CompetitionRegistration
from registrations.tests import (
    make_category,
    make_open_competition,
    make_registration,
    make_relay_competition,
    make_user,
)


def _manage(manager, member):
    managing.ask(member, managing.issue_invite(manager).key)
    managing.accept(manager, member.pk)


def _fields(person, **over):
    """What the browser sends for one ticked person: their form under its prefix."""
    data = {
        "first_name": person.first_name,
        "last_name": person.last_name,
        "gender": person.gender,
        "birth_year": person.birth_date.year if person.birth_date else "",
    }
    data.update(over)
    return {f"p{person.pk}-{name}": value for name, value in data.items()}


class RegisterManyTests(TestCase):
    def setUp(self):
        self.organizer = make_user("org", role=User.Role.ORGANIZER)
        self.coach = make_user(
            "coach", first_name="Ivan", last_name="Petrov", gender="M", birth_date=datetime.date(1985, 5, 5)
        )
        self.anna = make_user(
            "anna",
            first_name="Anna",
            last_name="Ivanova",
            gender="F",
            birth_date=datetime.date(2009, 4, 17),
            city="Taraz",
        )
        self.boris = make_user(
            "boris", first_name="Boris", last_name="Sokolov", gender="M", birth_date=datetime.date(2010, 1, 2)
        )
        _manage(self.coach, self.anna)
        _manage(self.coach, self.boris)
        self.comp = make_open_competition(submitted_by=self.organizer, registration_mode="self_only")
        self.cat = make_category(self.comp)
        self.client.force_login(self.coach)

    def _url(self, comp=None):
        with translation.override("en"):
            return reverse("registrations:register", args=[(comp or self.comp).pk])

    def _rows(self, response):
        return [(row.key, row.label) for row in response.context["rows"]]

    def test_without_members_or_in_a_relay_it_is_the_page_for_one(self):
        self.client.force_login(make_user("loner", gender="M", birth_date=datetime.date(1990, 1, 1)))
        self.assertTemplateUsed(self.client.get(self._url()), "registrations/register.html")
        self.client.force_login(self.coach)
        relay = make_relay_competition(submitted_by=self.organizer)
        self.assertTemplateUsed(self.client.get(self._url(relay)), "registrations/register.html")

    def test_the_reader_comes_first_then_the_members_by_last_name_each_filled_in_from_their_profile(self):
        response = self.client.get(self._url())
        self.assertTemplateUsed(response, "registrations/register_many.html")
        self.assertEqual(
            self._rows(response),
            [
                (str(self.coach.pk), "Ivan Petrov (you)"),
                (str(self.anna.pk), "Ivanova Anna"),
                (str(self.boris.pk), "Sokolov Boris"),
            ],
        )
        self.assertContains(response, f'name="p{self.anna.pk}-last_name" value="Ivanova"')
        self.assertContains(response, f'name="p{self.anna.pk}-city" value="Taraz"')

    def test_a_waiting_request_offers_nobody(self):
        carl = make_user("carl", gender="M", birth_date=datetime.date(2011, 1, 1))
        managing.ask(carl, managing.invite_of(self.coach).key)
        self.assertNotIn(str(carl.pk), [key for key, _ in self._rows(self.client.get(self._url()))])

    def test_whoever_is_registered_already_is_left_out_unless_the_event_takes_several(self):
        make_registration(self.comp, user=self.anna)
        self.assertNotIn(str(self.anna.pk), [key for key, _ in self._rows(self.client.get(self._url()))])
        several = make_open_competition(submitted_by=self.organizer, allow_multiple_registrations=True)
        make_registration(
            several, user=self.anna, first_name="Anna", last_name="Ivanova", birth_date=self.anna.birth_date
        )
        keys = [key for key, _ in self._rows(self.client.get(self._url(several)))]
        self.assertIn(str(self.anna.pk), keys)

    def test_a_profile_that_cannot_fill_a_self_only_form_is_listed_without_a_checkbox(self):
        self.boris.birth_date = None
        self.boris.save()
        response = self.client.get(self._url())
        self.assertContains(response, "Their profile has no gender or date of birth: ask them to complete it.")
        self.assertNotContains(response, f'name="person" value="{self.boris.pk}"')
        self.assertContains(response, f'name="person" value="{self.anna.pk}"')

    def test_an_event_that_lets_anyone_be_registered_offers_another_person_too(self):
        free = make_open_competition(submitted_by=self.organizer)
        response = self.client.get(self._url(free))
        self.assertEqual(self._rows(response)[-1], ("other", "Another person"))
        self.assertContains(response, 'name="pother-first_name" value=""')

    def test_the_ticked_are_registered_as_their_own_with_their_profile_data(self):
        data = {
            "person": [str(self.coach.pk), str(self.anna.pk)],
            **_fields(self.coach, category=self.cat.pk),
            **_fields(self.anna, category=self.cat.pk, first_name="Somebody", gender="M"),
        }
        response = self.client.post(self._url(), data)
        self.assertEqual(response.status_code, 302)
        own = CompetitionRegistration.objects.get(competition=self.comp, user=self.coach)
        hers = CompetitionRegistration.objects.get(competition=self.comp, user=self.anna)
        self.assertEqual(own.registered_by, self.coach)
        self.assertEqual(hers.registered_by, self.coach)
        self.assertEqual((hers.first_name, hers.gender), ("Anna", "F"))
        self.assertFalse(CompetitionRegistration.objects.filter(user=self.boris).exists())

    def test_one_who_cannot_be_registered_keeps_the_reason_and_the_others_are_registered(self):
        men = make_category(self.comp, name="Men", female=False)
        data = {
            "person": [str(self.coach.pk), str(self.anna.pk), str(self.boris.pk)],
            **_fields(self.coach, category=self.cat.pk),
            **_fields(self.anna, category=men.pk),
            **_fields(self.boris, category=self.cat.pk),
        }
        response = self.client.post(self._url(), data)
        self.assertEqual(response.status_code, 200)
        rows = {row.key: row for row in response.context["rows"]}
        self.assertTrue(rows[str(self.coach.pk)].entered and rows[str(self.boris.pk)].entered)
        refused = rows[str(self.anna.pk)]
        self.assertFalse(refused.entered)
        self.assertTrue(refused.checked)
        self.assertIn("category", refused.form.errors)
        self.assertEqual(
            set(CompetitionRegistration.objects.values_list("user", flat=True)), {self.coach.pk, self.boris.pk}
        )
        self.assertContains(response, "Registration submitted", count=2)
        self.assertNotContains(response, f'name="person" value="{self.coach.pk}"')

    def test_what_the_manager_adds_goes_into_the_registration_only(self):
        free = make_open_competition(submitted_by=self.organizer)
        free_cat = make_category(free)
        data = {"person": [str(self.anna.pk)], **_fields(self.anna, category=free_cat.pk, city="Shymkent")}
        self.assertEqual(self.client.post(self._url(free), data).status_code, 302)
        self.assertEqual(CompetitionRegistration.objects.get(user=self.anna).city, "Shymkent")
        self.anna.refresh_from_db()
        self.assertEqual(self.anna.city, "Taraz")

    def test_another_person_is_typed_in_and_belongs_to_the_reader(self):
        free = make_open_competition(submitted_by=self.organizer)
        free_cat = make_category(free)
        data = {
            "person": ["other"],
            "pother-first_name": "Kid",
            "pother-last_name": "Petrov",
            "pother-gender": "M",
            "pother-birth_year": 2016,
            "pother-category": free_cat.pk,
        }
        self.assertEqual(self.client.post(self._url(free), data).status_code, 302)
        reg = CompetitionRegistration.objects.get(competition=free)
        self.assertEqual((reg.first_name, reg.user, reg.registered_by), ("Kid", self.coach, self.coach))

    def test_a_forged_tick_is_refused_whole(self):
        stranger = make_user("stranger", gender="F", birth_date=datetime.date(2000, 1, 1))
        data = {"person": [str(self.anna.pk), str(stranger.pk)], **_fields(self.anna), **_fields(stranger)}
        self.assertEqual(self.client.post(self._url(), data).status_code, 403)
        self.assertEqual(self.client.post(self._url(), {"person": ["other"]}).status_code, 403)
        self.assertFalse(CompetitionRegistration.objects.exists())

    def test_nothing_ticked_says_so(self):
        response = self.client.post(self._url(), {})
        self.assertContains(response, "Tick at least one person.")
        self.assertFalse(CompetitionRegistration.objects.exists())

    def test_everyone_registered_already_says_so(self):
        for person in (self.coach, self.anna, self.boris):
            make_registration(self.comp, user=person)
        response = self.client.get(self._url())
        self.assertContains(response, "Everyone you could register here is registered already.")
        self.assertNotContains(response, 'id="registration-form"')

    def test_an_invite_only_event_lets_the_member_in_as_though_they_had_opened_its_link(self):
        closed = make_open_competition(submitted_by=self.organizer, registration_mode="self_only", invite_only=True)
        cat = make_category(closed)
        CompetitionInvite.objects.create(competition=closed, user=self.coach)
        self.assertFalse(can_see(self.anna, closed))
        data = {"person": [str(self.anna.pk)], **_fields(self.anna, category=cat.pk)}
        self.assertEqual(self.client.post(self._url(closed), data).status_code, 302)
        self.assertTrue(CompetitionInvite.objects.filter(competition=closed, user=self.anna).exists())
        CompetitionRegistration.objects.filter(user=self.anna).delete()
        self.assertTrue(can_see(self.anna, closed))

    def test_the_page_speaks_each_language(self):
        for lang in ("ru", "kk"):
            with self.subTest(lang), translation.override(lang):
                response = self.client.get(reverse("registrations:register", args=[self.comp.pk]))
                said = translation.gettext("%(name)s (you)") % {"name": "Ivan Petrov"}
                self.assertContains(response, said)
                self.assertNotEqual(said, "Ivan Petrov (you)")
