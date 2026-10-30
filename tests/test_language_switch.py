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


class ReaderOnAnotherLanguagesPageTests(TestCase):
    """A link from a chat opens in its sender's language, and the reader's own is another.

    Django reads the page named in `next` in the language the request is in -- the reader's own,
    since the switch's address has no prefix -- so it could not read a page in any other language
    and sent the reader back to it unchanged: the button did nothing.
    """

    def test_an_english_phone_on_a_russian_page_gets_the_english_page(self):
        response = _phone().post(reverse("set_language"), {"language": "en", "next": "/ru/news/"})
        self.assertEqual(response["Location"], "/en/news/")

    def test_a_reader_who_chose_kazakh_before_can_leave_a_russian_page(self):
        client = Client()
        client.post(reverse("set_language"), {"language": "kk", "next": "/ru/"})
        response = client.post(reverse("set_language"), {"language": "en", "next": "/ru/calendar/list/?event_type=1"})
        self.assertEqual(response["Location"], "/en/calendar/list/?event_type=1")

    def test_a_form_without_next_leaves_the_page_it_was_sent_from(self):
        """Django falls back to the referring page when `next` is missing, so that page's language counts."""
        response = _phone().post(reverse("set_language"), {"language": "kk"}, HTTP_REFERER="http://testserver/ru/news/")
        self.assertEqual(response["Location"], "http://testserver/kk/news/")


class LinksBackHomeTests(TestCase):
    """A link the site prints for itself must name the language the reader is already reading in.

    The navbar has done this for a while; the two error pages still sent people to a bare "/",
    which is the one address whose answer depends on who is asking -- the redirect at the heart of
    this bug. A reader who mistypes a URL should not have to be re-sorted into a language.
    """

    def test_the_not_found_page_offers_a_home_that_names_a_language(self):
        response = _phone().get("/en/no-such-page/")
        self.assertEqual(response.status_code, 404)
        # The button itself, not just any /en/ link -- the navbar carries one of those too.
        self.assertContains(response, '<a href="/en/" class="btn btn-primary">', status_code=404)


class SigningInAndOutKeepsThePageLanguageTests(TestCase):
    """The member read the Kazakh or English page; their browser says Russian, their profile nothing."""

    def setUp(self):
        from allauth.account.models import EmailAddress

        self.user = User.objects.create_user(
            username="reader", email="reader@example.com", password="Pass-12345!", role=User.Role.PARTICIPANT
        )
        EmailAddress.objects.create(user=self.user, email=self.user.email, verified=True, primary=True)
        self.client = Client(HTTP_ACCEPT_LANGUAGE="ru-RU,ru;q=0.9")

    def test_signing_in_lands_on_the_home_page_in_the_page_language(self):
        for language in ("kk", "en"):
            with self.subTest(language=language):
                self.client.logout()
                response = self.client.post(
                    f"/{language}/accounts/login/", {"login": "reader@example.com", "password": "Pass-12345!"}
                )
                self.assertEqual(response["Location"], f"/{language}/")

    def test_signing_out_lands_on_the_home_page_in_the_page_language(self):
        for language in ("kk", "en"):
            with self.subTest(language=language):
                self.client.force_login(self.user)
                response = self.client.post(f"/{language}/accounts/logout/")
                self.assertEqual(response["Location"], f"/{language}/")

    def test_a_member_who_chose_a_language_still_lands_in_it(self):
        self.user.preferred_language = "en"
        self.user.save(update_fields=["preferred_language"])
        response = self.client.post("/kk/accounts/login/", {"login": "reader@example.com", "password": "Pass-12345!"})
        self.assertEqual(self.client.get(response["Location"])["Location"], "/en/")

    def test_a_language_chosen_with_the_buttons_still_wins_after_signing_out(self):
        self.client.cookies["django_language"] = "en"
        self.client.force_login(self.user)
        response = self.client.post("/kk/accounts/logout/")
        self.assertEqual(self.client.get(response["Location"])["Location"], "/en/")

    def test_a_next_page_is_kept_as_it_was(self):
        response = self.client.post(
            "/kk/accounts/login/?next=/en/calendar/", {"login": "reader@example.com", "password": "Pass-12345!"}
        )
        self.assertEqual(response["Location"], "/en/calendar/")
