"""Managing another member's registrations and photos (issue #315): the link, the requests, the rights."""

import datetime
import uuid

from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext

from accounts import managing
from accounts.models import ManagedMember, ManagerInvite, User


def _user(name):
    return _user_with_role(name, User.Role.PARTICIPANT)


def _user_with_role(name, role):
    return User.objects.create_user(username=name, email=f"{name}@example.com", password="pw", role=role)


class InviteTests(TestCase):
    def setUp(self):
        self.coach = _user("coach")

    def test_a_new_link_shuts_the_old_one(self):
        old = managing.issue_invite(self.coach).key
        new = managing.issue_invite(self.coach).key
        self.assertNotEqual(old, new)
        self.assertIsNone(managing.find_invite(old))
        self.assertEqual(managing.find_invite(new).manager, self.coach)

    def test_a_link_lasts_a_month(self):
        invite = managing.issue_invite(self.coach)
        ManagerInvite.objects.filter(pk=invite.pk).update(created_at=timezone.now() - datetime.timedelta(days=31))
        self.assertIsNone(managing.find_invite(invite.key))
        ManagerInvite.objects.filter(pk=invite.pk).update(created_at=timezone.now() - datetime.timedelta(days=29))
        self.assertIsNotNone(managing.find_invite(invite.key))

    def test_a_deleted_link_works_no_more(self):
        key = managing.issue_invite(self.coach).key
        managing.delete_invite(self.coach)
        self.assertIsNone(managing.find_invite(key))
        self.assertIsNone(managing.invite_of(self.coach))

    def test_neither_a_new_link_nor_its_end_rejects_anyone_waiting(self):
        anna = _user("anna")
        managing.ask(anna, managing.issue_invite(self.coach).key)
        managing.issue_invite(self.coach)
        managing.delete_invite(self.coach)
        self.assertEqual([r.member for r in managing.waiting(self.coach)], [anna])


class AskingTests(TestCase):
    def setUp(self):
        self.coach, self.anna = _user("coach"), _user("anna")
        self.key = managing.issue_invite(self.coach).key

    def test_asking_makes_a_request_that_waits_for_the_manager(self):
        self.assertEqual(managing.ask(self.anna, self.key), managing.ASKED)
        self.assertEqual([r.member for r in managing.waiting(self.coach)], [self.anna])
        self.assertFalse(managing.acts_for(self.coach, self.anna.pk))

    def test_each_reason_not_to_ask_is_told_apart(self):
        self.assertEqual(managing.ask(self.anna, uuid.uuid4()), managing.INVALID)
        self.assertEqual(managing.ask(self.coach, self.key), managing.OWN)
        managing.ask(self.anna, self.key)
        self.assertEqual(managing.ask(self.anna, self.key), managing.WAITING)
        managing.accept(self.coach, self.anna.pk)
        self.assertEqual(managing.ask(self.anna, self.key), managing.MANAGED)
        self.assertEqual(ManagedMember.objects.count(), 1)

    def test_nobody_manages_themselves(self):
        with self.assertRaises(IntegrityError):
            ManagedMember.objects.create(manager=self.coach, member=self.coach)


class DecidingTests(TestCase):
    def setUp(self):
        self.coach = _user("coach")
        self.anna, self.boris, self.carl = _user("anna"), _user("boris"), _user("carl")
        key = managing.issue_invite(self.coach).key
        for member in (self.anna, self.boris, self.carl):
            managing.ask(member, key)

    def test_accepting_one_gives_the_right_for_that_one(self):
        self.assertTrue(managing.accept(self.coach, self.anna.pk))
        self.assertTrue(managing.acts_for(self.coach, self.anna.pk))
        self.assertFalse(managing.acts_for(self.coach, self.boris.pk))
        self.assertEqual(managing.member_ids(self.coach), {self.anna.pk})

    def test_a_rejected_request_disappears_and_may_come_again(self):
        self.assertTrue(managing.reject(self.coach, self.anna.pk))
        self.assertFalse(ManagedMember.objects.filter(member=self.anna).exists())
        self.assertEqual(managing.ask(self.anna, managing.invite_of(self.coach).key), managing.ASKED)

    def test_all_at_once(self):
        self.assertEqual(managing.accept_all(self.coach), 3)
        self.assertEqual(managing.member_ids(self.coach), {self.anna.pk, self.boris.pk, self.carl.pk})
        managing.drop(self.coach, self.carl.pk)
        managing.ask(self.carl, managing.invite_of(self.coach).key)
        self.assertEqual(managing.reject_all(self.coach), 1)
        self.assertEqual(managing.member_ids(self.coach), {self.anna.pk, self.boris.pk})

    def test_either_side_ends_it_and_nothing_is_left(self):
        managing.accept_all(self.coach)
        self.assertTrue(managing.drop(self.coach, self.anna.pk))
        self.assertTrue(managing.leave(self.boris, self.coach.pk))
        self.assertEqual(managing.member_ids(self.coach), {self.carl.pk})
        self.assertFalse(ManagedMember.objects.filter(member__in=[self.anna, self.boris]).exists())

    def test_the_member_withdraws_a_waiting_request(self):
        self.assertTrue(managing.leave(self.anna, self.coach.pk))
        self.assertNotIn(self.anna, [r.member for r in managing.waiting(self.coach)])


class ChainTests(TestCase):
    def test_two_members_may_manage_each_other_and_rights_do_not_pass_along(self):
        a, b, c = _user("a"), _user("b"), _user("c")
        for manager, member in ((a, b), (b, a), (b, c)):
            managing.ask(member, managing.issue_invite(manager).key)
            managing.accept(manager, member.pk)
        self.assertTrue(managing.acts_for(a, b.pk) and managing.acts_for(b, a.pk))
        self.assertTrue(managing.acts_for(b, c.pk))
        self.assertFalse(managing.acts_for(a, c.pk))


class JoinPageTests(TestCase):
    """The link's page: it asks the member by a button and says plainly why it cannot."""

    def setUp(self):
        self.coach = User.objects.create_user(
            username="coach",
            email="coach@example.com",
            password="pw",
            role=User.Role.PARTICIPANT,
            first_name="Ivan",
            last_name="Petrov",
        )
        self.anna = _user("anna")
        self.key = managing.issue_invite(self.coach).key
        self.url = f"/en/accounts/managing/join/{self.key}/"

    def test_a_visitor_signs_in_first_and_comes_back(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])
        self.assertIn(f"next=/en/accounts/managing/join/{self.key}/", response["Location"])

    def test_an_account_not_confirmed_is_sent_to_confirm_it(self):
        self.client.force_login(_user_with_role("guest", User.Role.GUEST))
        response = self.client.get(self.url)
        self.assertRedirects(response, "/en/accounts/profile/", fetch_redirect_response=False)
        self.assertFalse(ManagedMember.objects.exists())

    def test_opening_names_who_asks_and_grants_nothing(self):
        self.client.force_login(self.anna)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ivan Petrov")
        self.assertContains(response, '<button type="submit" class="btn btn-primary">')
        self.assertEqual(response["X-Robots-Tag"], "noindex")
        self.assertFalse(ManagedMember.objects.exists())

    def test_the_button_asks_and_the_request_waits(self):
        self.client.force_login(self.anna)
        response = self.client.post(self.url)
        self.assertRedirects(response, "/en/accounts/profile/#my-managers", fetch_redirect_response=False)
        row = ManagedMember.objects.get()
        self.assertEqual((row.manager, row.member, row.accepted_at), (self.coach, self.anna, None))

    def test_each_reason_not_to_ask_is_said_plainly(self):
        stale_key = self.key
        self.key = managing.issue_invite(self.coach).key
        expired = _user("expired")
        run_out = managing.issue_invite(expired).key
        ManagerInvite.objects.filter(manager=expired).update(created_at=timezone.now() - ManagerInvite.LIFETIME)
        invalid = "This link is not valid or has probably expired. Ask whoever sent it for a new one."
        own = "This is your own link: send it to the people whose registrations and photos you will manage."
        cases = [
            ("a key never made", self.anna, uuid.uuid4(), 404, invalid),
            ("a key made new since", self.anna, stale_key, 404, invalid),
            ("a link run out", self.anna, run_out, 404, invalid),
            ("one's own", self.coach, self.key, 200, own),
        ]
        for label, user, key, status, text in cases:
            with self.subTest(label):
                self.client.force_login(user)
                url = f"/en/accounts/managing/join/{key}/"
                for response in (self.client.get(url), self.client.post(url)):
                    self.assertContains(response, text, status_code=status)
                    self.assertNotContains(response, 'class="btn btn-primary"', status_code=status)
        self.assertFalse(ManagedMember.objects.exists())

    def test_asking_twice_says_the_request_waits_and_then_that_it_was_accepted(self):
        self.client.force_login(self.anna)
        self.client.post(self.url)
        self.assertContains(self.client.get(self.url), "Your request to Ivan Petrov is already waiting to be accepted.")
        managing.accept(self.coach, self.anna.pk)
        response = self.client.post(self.url)
        self.assertContains(response, "Ivan Petrov already manages your registrations and photos.")
        self.assertEqual(ManagedMember.objects.count(), 1)

    def test_the_page_speaks_each_language(self):
        self.client.force_login(self.anna)
        for lang in ("ru", "kk"):
            with self.subTest(lang), translation.override(lang):
                response = self.client.get(f"/{lang}/accounts/managing/join/{self.key}/")
                self.assertContains(response, gettext("Allow"))
                self.assertNotEqual(gettext("Allow"), "Allow")


class ProfileSectionTests(TestCase):
    """The profile's two sections: the link, the requests waiting, the members, and both ways out."""

    profile = "/en/accounts/profile/"

    def setUp(self):
        self.coach = _user("coach")
        self.anna = User.objects.create_user(
            username="anna",
            email="anna@example.com",
            password="pw",
            role=User.Role.PARTICIPANT,
            first_name="Anna",
            last_name="Ivanova",
            team="Snow Leopards",
            city="Taraz",
            gender=User.Gender.FEMALE,
            birth_date=datetime.date(2009, 4, 17),
        )
        self.client.force_login(self.coach)

    def _post(self, name, *args):
        with translation.override("en"):
            return self.client.post(reverse(name, args=args))

    def test_a_confirmed_member_sees_both_sections_and_an_unconfirmed_one_neither(self):
        response = self.client.get(self.profile)
        self.assertContains(response, 'id="my-managers"')
        self.assertContains(response, 'id="managed-members"')
        self.client.force_login(_user_with_role("guest", User.Role.GUEST))
        response = self.client.get(self.profile)
        self.assertNotContains(response, 'id="my-managers"')
        self.assertNotContains(response, 'id="managed-members"')

    def test_the_link_is_made_shared_made_new_and_deleted(self):
        response = self._post("account_managing_issue")
        self.assertRedirects(response, f"{self.profile}#managed-members", fetch_redirect_response=False)
        first = f"http://testserver/en/accounts/managing/join/{managing.invite_of(self.coach).key}/"
        self.assertContains(self.client.get(self.profile), f'data-share-url="{first}"')
        self._post("account_managing_issue")
        page = self.client.get(self.profile)
        self.assertNotContains(page, first)
        self.assertContains(page, f"/en/accounts/managing/join/{managing.invite_of(self.coach).key}/")
        self._post("account_managing_delete")
        self.assertIsNone(managing.invite_of(self.coach))
        self.assertContains(self.client.get(self.profile), "Create link")

    def test_a_link_run_out_says_when_and_offers_a_new_one(self):
        managing.issue_invite(self.coach)
        ManagerInvite.objects.update(created_at=timezone.now() - ManagerInvite.LIFETIME)
        page = self.client.get(self.profile)
        self.assertContains(page, "Your link expired on")
        self.assertContains(page, "Create link")
        self.assertNotContains(page, "/accounts/managing/join/")

    def test_a_request_waits_with_what_tells_the_member_apart_and_is_accepted(self):
        managing.ask(self.anna, managing.issue_invite(self.coach).key)
        page = self.client.get(self.profile)
        self.assertContains(page, "Waiting for your answer")
        for text in ("Ivanova", "Anna", "Snow Leopards", "2009"):
            self.assertContains(page, text)
        self.assertNotContains(page, "17.04.2009")
        self.assertNotContains(page, "Accept all")
        self._post("account_managing_accept", self.anna.pk)
        self.assertTrue(managing.acts_for(self.coach, self.anna.pk))
        page = self.client.get(self.profile)
        self.assertNotContains(page, "Waiting for your answer")
        for text in ("Ivanova", "Anna", "04/17/2009", "Female", "Taraz", "Snow Leopards"):
            self.assertContains(page, text)
        self.assertNotContains(page, "anna@example.com")

    def test_requests_are_rejected_one_by_one_or_answered_all_at_once(self):
        key = managing.issue_invite(self.coach).key
        boris, carl, dana = _user("boris"), _user("carl"), _user("dana")
        for member in (self.anna, boris):
            managing.ask(member, key)
        self.assertContains(self.client.get(self.profile), "Accept all")
        self._post("account_managing_reject", boris.pk)
        self.assertEqual([row.member for row in managing.waiting(self.coach)], [self.anna])
        for member in (boris, carl):
            managing.ask(member, key)
        self._post("account_managing_accept_all")
        self.assertEqual(managing.member_ids(self.coach), {self.anna.pk, boris.pk, carl.pk})
        managing.ask(dana, key)
        self._post("account_managing_reject_all")
        self.assertFalse(managing.waiting(self.coach).exists())

    def test_either_side_ends_it_from_its_own_section(self):
        managing.ask(self.anna, managing.issue_invite(self.coach).key)
        managing.accept(self.coach, self.anna.pk)
        self._post("account_managing_drop", self.anna.pk)
        self.assertFalse(ManagedMember.objects.exists())
        managing.ask(self.anna, managing.invite_of(self.coach).key)
        self.client.force_login(self.anna)
        page = self.client.get(self.profile)
        self.assertContains(page, "Waiting for confirmation")
        self.assertContains(page, "Withdraw")
        managing.accept(self.coach, self.anna.pk)
        self.assertContains(self.client.get(self.profile), "Remove")
        response = self._post("account_managing_leave", self.coach.pk)
        self.assertRedirects(response, f"{self.profile}#my-managers", fetch_redirect_response=False)
        self.assertFalse(ManagedMember.objects.exists())

    def test_an_id_in_the_address_reaches_only_ones_own_rows(self):
        managing.ask(self.anna, managing.issue_invite(self.coach).key)
        stranger = _user("stranger")
        self.client.force_login(stranger)
        for name, args in (
            ("account_managing_accept", (self.anna.pk,)),
            ("account_managing_accept_all", ()),
            ("account_managing_drop", (self.anna.pk,)),
            ("account_managing_leave", (self.coach.pk,)),
            ("account_managing_delete", ()),
        ):
            self._post(name, *args)
        row = ManagedMember.objects.get()
        self.assertIsNone(row.accepted_at)
        self.assertIsNotNone(managing.invite_of(self.coach))

    def test_the_buttons_take_a_post_from_a_confirmed_member_only(self):
        self.assertEqual(self.client.get(reverse("account_managing_issue")).status_code, 405)
        self.client.logout()
        response = self._post("account_managing_issue")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])
        self.assertIsNone(managing.invite_of(self.coach))

    def test_the_sections_speak_each_language(self):
        managing.ask(self.coach, managing.issue_invite(self.anna).key)
        managing.accept(self.anna, self.coach.pk)
        for lang in ("ru", "kk"):
            with self.subTest(lang), translation.override(lang):
                page = self.client.get(f"/{lang}/accounts/profile/")
                for text in (
                    gettext("Who may manage my registrations and photos"),
                    gettext("Whose registrations and photos I manage"),
                    translation.pgettext("a person from a list", "Remove"),
                ):
                    self.assertContains(page, text)
                heading = "Whose registrations and photos I manage"
                self.assertNotEqual(gettext(heading), heading)
