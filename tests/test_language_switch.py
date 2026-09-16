"""Switching the language the way a phone does it.

Every locale test the suite had started from a browser that already carried "django_language=ru"
-- the e2e fixture sets it for all of them -- so the path a real English-speaking device takes was
never walked: no cookie at all, Accept-Language saying English, and a reader who then asks for
Russian. Two readers reported that their choice did not stick, which is what sent us looking.
"""

from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User

EN_PHONE = "en-US,en;q=0.9"


def _phone(user=None):
    client = Client(HTTP_ACCEPT_LANGUAGE=EN_PHONE)
    if user is not None:
        client.force_login(user)
    return client


class GuestOnAnEnglishPhoneTests(TestCase):
    def test_the_site_opens_in_the_language_the_device_asks_for(self):
        response = _phone().get("/")
        self.assertEqual(response["Location"], "/en/")

    def test_choosing_russian_lands_on_the_russian_page(self):
        client = _phone()
        client.get("/")
        response = client.post(reverse("set_language"), {"language": "ru", "next": "/en/"})
        self.assertEqual(response["Location"], "/ru/")
        self.assertEqual(client.cookies["django_language"].value, "ru")

    def test_the_choice_holds_when_the_bare_address_is_opened_again(self):
        client = _phone()
        client.post(reverse("set_language"), {"language": "ru", "next": "/en/"})
        self.assertEqual(client.get("/")["Location"], "/ru/")

    def test_the_choice_keeps_the_page_the_reader_was_on(self):
        client = _phone()
        response = client.post(reverse("set_language"), {"language": "ru", "next": "/en/calendar/"})
        self.assertEqual(response["Location"], "/ru/calendar/")


class ReaderSignedInOnAnEnglishPhoneTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="phone", email="phone@example.com", password="Pass1234!")

    def test_the_choice_is_written_to_the_profile(self):
        client = _phone(self.user)
        client.post(reverse("set_language"), {"language": "ru", "next": "/en/"})
        self.user.refresh_from_db()
        self.assertEqual(self.user.preferred_language, "ru")

    def test_the_profile_carries_the_choice_when_the_cookie_is_gone(self):
        """A browser that drops the cookie must not undo a signed-in reader's choice."""
        client = _phone(self.user)
        client.post(reverse("set_language"), {"language": "ru", "next": "/en/"})
        client.cookies.pop("django_language", None)
        self.assertEqual(client.get("/")["Location"], "/ru/")

    def test_a_deeper_address_follows_the_profile_too(self):
        client = _phone(self.user)
        client.post(reverse("set_language"), {"language": "ru", "next": "/en/"})
        client.cookies.pop("django_language", None)
        self.assertEqual(client.get("/calendar/")["Location"], "/ru/calendar/")

    def test_an_address_that_names_english_stays_english(self):
        """A prefix is an explicit request and outranks the profile -- /en/ is the same page for
        everyone who asks for it, reader and crawler alike."""
        client = _phone(self.user)
        client.post(reverse("set_language"), {"language": "ru", "next": "/en/"})
        response = client.get("/en/calendar/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["request"].LANGUAGE_CODE, "en")
