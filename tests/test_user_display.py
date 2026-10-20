"""The name allauth uses for a member: "Successfully signed in as ..." and its emails."""

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from accounts.adapters import user_display
from accounts.models import User


def _member(**fields):
    defaults = {
        "username": "denis",
        "email": "denis@example.com",
        "password": "pw-12345!",
        "role": User.Role.PARTICIPANT,
    }
    defaults.update(fields)
    return User.objects.create_user(**defaults)


class UserDisplayTests(TestCase):
    def test_the_name_from_the_profile_comes_first(self):
        self.assertEqual(user_display(_member(first_name="Denis", last_name="Chernykh")), "Denis Chernykh")

    def test_then_the_address_they_sign_in_with(self):
        self.assertEqual(user_display(_member()), "denis@example.com")

    def test_the_username_only_when_there_is_nothing_else(self):
        self.assertEqual(user_display(_member(email="")), "denis")

    def test_the_sign_in_message_greets_the_member_by_name(self):
        _member(first_name="Denis", last_name="Chernykh")
        response = self.client.post(
            reverse("account_login"), {"login": "denis@example.com", "password": "pw-12345!"}, follow=True
        )
        texts = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any("Denis Chernykh" in t for t in texts), texts)
        self.assertFalse(any(" denis." in t for t in texts), texts)
