"""Managing another member's registrations and photos (issue #315): the link, the requests, the rights."""

import datetime
import uuid

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from accounts import managing
from accounts.models import ManagedMember, ManagerInvite, User


def _user(name):
    return User.objects.create_user(
        username=name, email=f"{name}@example.com", password="pw", role=User.Role.PARTICIPANT
    )


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
