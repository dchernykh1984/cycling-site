"""A manager's hand on a member's registrations (issue #315): change and cancel them, see them, and
the organizers' "Submitted by"."""

import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from accounts import managing
from accounts.models import User
from registrations.models import CompetitionRegistration
from registrations.tests import make_open_competition, make_registration, make_relay_competition, make_user


def _en(name, *args):
    with translation.override("en"):
        return reverse(name, args=args)


def _manage(manager, member):
    managing.ask(member, managing.issue_invite(manager).key)
    managing.accept(manager, member.pk)


class MembersRegistrationsTests(TestCase):
    def setUp(self):
        self.organizer = make_user("org", role=User.Role.ORGANIZER)
        self.coach = make_user("coach", first_name="Ivan", last_name="Petrov")
        self.anna = make_user(
            "anna", first_name="Anna", last_name="Ivanova", gender="F", birth_date=datetime.date(2009, 4, 17)
        )
        _manage(self.coach, self.anna)
        self.comp = make_open_competition(submitted_by=self.organizer, registration_mode="self_only")
        self.reg = make_registration(
            self.comp,
            user=self.anna,
            registered_by=self.anna,
            first_name="Anna",
            last_name="Ivanova",
            gender="F",
            birth_date=datetime.date(2009, 4, 17),
        )
        self.edit = _en("registrations:edit_registration", self.comp.pk, self.reg.pk)
        self.cancel = _en("registrations:delete_registration", self.comp.pk, self.reg.pk)
        self.participants = _en("registrations:participant_list", self.comp.pk)

    def test_a_manager_changes_and_cancels_a_members_entry_as_the_member_would(self):
        self.client.force_login(self.coach)
        page = self.client.get(self.edit)
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, 'name="is_approved"')
        data = {"first_name": "Anna", "last_name": "Ivanova", "birth_date": "2009-04-17", "gender": "F"}
        self.assertEqual(self.client.post(self.edit, {**data, "city": "Taraz"}).status_code, 302)
        self.reg.refresh_from_db()
        self.assertEqual(self.reg.city, "Taraz")
        self.assertEqual(self.client.post(self.cancel).status_code, 302)
        self.assertFalse(CompetitionRegistration.objects.filter(pk=self.reg.pk).exists())

    def test_no_right_once_it_ends_while_it_waits_or_along_a_chain(self):
        boris, carl = make_user("boris"), make_user("carl")
        managing.ask(boris, managing.invite_of(self.coach).key)
        _manage(self.anna, carl)
        managing.drop(self.coach, self.anna.pk)
        self.client.force_login(self.coach)
        for member in (self.anna, boris, carl):
            with self.subTest(member.username):
                reg = self.reg if member == self.anna else make_registration(self.comp, user=member)
                self.assertEqual(
                    self.client.get(_en("registrations:edit_registration", self.comp.pk, reg.pk)).status_code, 403
                )
                self.assertEqual(
                    self.client.post(_en("registrations:delete_registration", self.comp.pk, reg.pk)).status_code, 403
                )
        self.assertTrue(CompetitionRegistration.objects.filter(pk=self.reg.pk).exists())

    def test_the_participant_list_offers_the_buttons_on_a_members_entry_and_on_no_one_elses(self):
        self.client.force_login(self.coach)
        page = self.client.get(self.participants)
        self.assertContains(page, self.edit)
        self.assertContains(page, "Cancel this registration?")
        self.client.force_login(make_user("stranger"))
        self.assertNotContains(self.client.get(self.participants), self.edit)

    def test_a_members_entry_hidden_until_approved_is_listed_for_their_manager(self):
        self.comp.require_approval = True
        self.comp.show_unapproved_in_list = False
        self.comp.save()
        self.client.force_login(self.coach)
        self.assertContains(self.client.get(self.participants), "Ivanova")
        self.client.force_login(make_user("stranger"))
        self.assertNotContains(self.client.get(self.participants), "Ivanova")

    def test_the_profile_lists_a_members_open_entries_under_their_name_and_keeps_the_history_ones_own(self):
        self.client.force_login(self.coach)
        response = self.client.get("/en/accounts/profile/")
        self.assertEqual(response.context["active_registrations"], [self.reg])
        self.assertEqual(response.context["registrations"], [])
        self.assertContains(response, "Ivanova Anna")
        self.assertContains(response, self.edit)

    def test_a_members_relay_entry_is_named_by_its_team_in_the_profile(self):
        relay = make_relay_competition(submitted_by=self.organizer)
        make_registration(relay, user=self.anna, first_name="", last_name="", participant_names="Anna I.<BR>Dana B.")
        self.client.force_login(self.coach)
        self.assertContains(self.client.get("/en/accounts/profile/"), "Anna I.<BR>Dana B.")

    def test_organizers_see_who_submitted_an_entry_for_someone_else(self):
        self.client.force_login(self.organizer)
        with translation.override("en"):
            said = translation.pgettext("registration", "Submitted by") + ": Ivan Petrov"
        self.assertNotContains(self.client.get(self.participants), said)
        boris = make_user("boris", first_name="Boris", last_name="Sokolov")
        _manage(self.coach, boris)
        make_registration(self.comp, user=boris, registered_by=self.coach, first_name="Boris", last_name="Sokolov")
        page = self.client.get(self.participants)
        self.assertContains(page, said, count=1)
        self.assertNotContains(page, "<th>Submitted by")
        self.client.force_login(self.coach)
        self.assertNotContains(self.client.get(self.participants), said)
