"""The role a person holds, and asking for a different one.

The profile used to state the role in one line among the email and the birth date, which says
nothing about what else exists or that stepping down is possible. It is its own section now, and
the request goes to the owners as mail -- nothing is granted automatically.
"""

from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from accounts.views import role_ladder
from tests.language_urls import in_language


def _user(username, role=User.Role.PARTICIPANT):
    return User.objects.create_user(username=username, email=f"{username}@example.com", password="Pass1234!", role=role)


class RoleLadderTests(TestCase):
    def test_every_role_is_listed_weakest_first(self):
        ladder = role_ladder(_user("ladder"))
        self.assertEqual([r["value"] for r in ladder], User.ROLE_HIERARCHY)

    def test_exactly_one_rung_is_the_readers_own(self):
        ladder = role_ladder(_user("mine", role=User.Role.ORGANIZER))
        current = [r for r in ladder if r["is_current"]]
        self.assertEqual([r["value"] for r in current], [User.Role.ORGANIZER])


class ProfileSectionTests(TestCase):
    def setUp(self):
        self.user = _user("profile_role", role=User.Role.ORGANIZER)
        self.client.force_login(self.user)

    def _page(self):
        return self.client.get(in_language(reverse("account_profile"), "en"))

    def test_the_section_lists_the_whole_ladder(self):
        page = self._page()
        for role in User.Role.choices:
            self.assertContains(page, role[1])

    def test_the_current_role_is_the_bold_one(self):
        self.assertContains(self._page(), "<strong>Organizer</strong>", html=False)

    def test_it_sits_between_the_sign_in_methods_and_contacting_the_owners(self):
        body = self._page().content.decode()
        self.assertLess(body.index('id="signin-methods"'), body.index('id="role"'))
        self.assertLess(body.index('id="role"'), body.index("Contact site owners"))

    def test_a_participant_is_offered_the_request_button(self):
        self.assertContains(self._page(), reverse("account_request_role"))

    def test_a_guest_sees_the_ladder_without_the_button(self):
        self.client.force_login(_user("guest_role", role=User.Role.GUEST))
        page = self._page()
        self.assertContains(page, "Organizer")
        self.assertNotContains(page, reverse("account_request_role"))


class RequestRoleTests(TestCase):
    def setUp(self):
        self.user = _user("asker", role=User.Role.PARTICIPANT)
        self.client.force_login(self.user)
        self.url = in_language(reverse("account_request_role"), "en")

    def test_the_form_offers_every_role_except_the_one_held(self):
        offered = [value for value, _label in self.client.get(self.url).context["form"].fields["role"].choices]
        self.assertNotIn(User.Role.PARTICIPANT, offered)
        self.assertEqual(offered, [r for r in User.ROLE_HIERARCHY if r != User.Role.PARTICIPANT])

    def test_a_lower_role_may_be_asked_for(self):
        """An organizer who has stopped running races would rather not keep the buttons."""
        self.client.force_login(_user("stepping_down", role=User.Role.ORGANIZER))
        offered = [value for value, _label in self.client.get(self.url).context["form"].fields["role"].choices]
        self.assertIn(User.Role.PARTICIPANT, offered)

    def test_sending_mails_the_owners(self):
        response = self.client.post(self.url, {"role": User.Role.ORGANIZER, "reason": "I run two races a year."})
        self.assertRedirects(response, reverse("account_profile"))
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertIn("Role request", sent.subject)
        self.assertIn("Organizer", sent.body)
        self.assertIn("I run two races a year.", sent.body)
        self.assertIn(self.user.email, sent.body)

    def test_it_goes_to_the_same_mailbox_as_the_contact_form(self):
        from django.conf import settings

        self.client.post(self.url, {"role": User.Role.ORGANIZER, "reason": "Because."})
        self.assertEqual(mail.outbox[0].to, [settings.DEFAULT_FROM_EMAIL])

    def test_a_reason_is_required(self):
        response = self.client.post(self.url, {"role": User.Role.ORGANIZER, "reason": ""})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_a_role_that_is_not_on_the_ladder_is_refused(self):
        response = self.client.post(self.url, {"role": "president", "reason": "Why not."})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_nothing_is_granted_by_asking(self):
        self.client.post(self.url, {"role": User.Role.OWNER, "reason": "Please."})
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, User.Role.PARTICIPANT)

    def test_a_burst_of_requests_is_throttled(self):
        """The mailbox is shared with the contact form, and so is the cooldown."""
        self.client.post(self.url, {"role": User.Role.ORGANIZER, "reason": "First."})
        self.client.post(self.url, {"role": User.Role.ADMIN, "reason": "Second."})
        self.assertEqual(len(mail.outbox), 1)

    def test_a_guest_may_not_ask(self):
        self.client.force_login(_user("guest_asker", role=User.Role.GUEST))
        response = self.client.get(self.url)
        self.assertNotEqual(response.status_code, 200)

    def test_the_cooldown_is_released_when_the_mail_fails(self):
        from unittest.mock import patch

        self.user.last_mail_action_at = None
        self.user.save(update_fields=["last_mail_action_at"])
        with patch("accounts.views.send_mail", side_effect=RuntimeError("smtp down")):
            self.client.post(self.url, {"role": User.Role.ORGANIZER, "reason": "Trying."})
        self.user.refresh_from_db()
        self.assertIsNone(self.user.last_mail_action_at)

    def test_a_successful_request_stamps_the_cooldown(self):
        before = timezone.now()
        self.client.post(self.url, {"role": User.Role.ORGANIZER, "reason": "Yes."})
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.last_mail_action_at)
        self.assertGreaterEqual(self.user.last_mail_action_at, before)
