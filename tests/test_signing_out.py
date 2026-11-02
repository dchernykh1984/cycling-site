"""Signing out keeps the reader where they were: on the page, and in the look they had.

Signing out from the header landed on the home page, and drawn in the default skin -- or in one the
browser chose as a guest long ago -- rather than in the member's own.
"""

import datetime

from django.test import TestCase, override_settings
from django.utils.translation import gettext
from django.utils.translation import override as translation_override

from accounts.models import User
from calendar_app.models import Competition
from cycling_site import skins
from cycling_site.middleware import SignedOutMiddleware

UPCOMING = datetime.date.today() + datetime.timedelta(days=30)


class SigningOutStaysOnThePageTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user(
            username="leaving", email="leaving@example.com", password="pw", role=User.Role.ORGANIZER
        )
        self.client.force_login(self.member)

    def sign_out(self, page):
        language = page.split("/")[1]
        return self.client.post(f"/{language}/accounts/logout/", {"next": page})

    def test_the_header_s_sign_out_form_names_the_page_in_every_skin(self):
        for theme in ("light", "orange", "ubt-dark"):
            with self.subTest(theme=theme):
                self.member.theme = theme
                self.member.save(update_fields=["theme"])
                html = self.client.get("/en/calendar/list/?view=day").content.decode()
                form = html[html.index('action="/en/accounts/logout/"') :]
                self.assertIn('name="next" value="/en/calendar/list/?view=day"', form[: form.index("</form>")])

    def test_signing_out_returns_to_the_page_and_the_mark_goes_with_it(self):
        response = self.sign_out("/en/calendar/list/?view=day")
        self.assertEqual(response["Location"], "/en/calendar/list/?view=day")
        page = self.client.get(response["Location"])
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.cookies[SignedOutMiddleware.COOKIE]["max-age"], 0)

    def test_a_page_shut_to_guests_gives_way_to_the_home_page_in_its_language(self):
        own = Competition.objects.create(
            title_ru="Still under review",
            date_start=UPCOMING,
            status=Competition.Status.PENDING_APPROVAL,
            submitted_by=self.member,
        )
        pages = {
            "the sign-in form": "/kk/accounts/profile/",
            "a refusal": f"/kk/calendar/{own.pk}/edit/",
            "not found": f"/kk/calendar/{own.pk}/",
        }
        with translation_override("kk"):
            signed_out = gettext("You have signed out.")
        for guest_gets, page in pages.items():
            with self.subTest(guest_gets=guest_gets):
                self.client.force_login(self.member)
                landed = self.client.get(self.sign_out(page)["Location"])
                self.assertEqual(landed["Location"], "/kk/")
                self.assertEqual(landed.cookies[SignedOutMiddleware.COOKIE]["max-age"], 0)
                # Only for this reader, once: kept by a browser, it would bar the member from the page.
                self.assertIn("no-store", landed["Cache-Control"])
                # A refusal or a "not found" is drawn before it gives way, and must not use it up.
                self.assertContains(self.client.get(landed["Location"]), signed_out)

    def test_without_the_mark_such_a_page_answers_a_guest_as_before(self):
        self.client.logout()
        self.assertTrue(self.client.get("/kk/accounts/profile/")["Location"].startswith("/kk/accounts/login/"))


class SigningOutKeepsTheSkinTests(TestCase):
    def test_the_guest_keeps_the_member_s_skin_over_the_one_chosen_as_a_guest(self):
        member = User.objects.create_user(username="dark", email="dark@example.com", password="pw", theme="dark")
        self.client.cookies[skins.COOKIE] = "light"
        self.client.force_login(member)
        response = self.client.post("/ru/accounts/logout/", {"next": "/ru/news/"})
        self.assertEqual(response.cookies[skins.COOKIE].value, "dark")
        self.assertContains(self.client.get("/ru/news/"), 'data-skin="dark"')

    # Set here, not taken from the settings: a default that is the skin on offer would hide the offer.
    @override_settings(DEFAULT_SKIN="light", SKIN_OFFER="orange")
    def test_and_is_not_asked_again_to_try_a_skin_tried_as_a_member(self):
        member = User.objects.create_user(
            username="tried", email="tried@example.com", password="pw", theme="dark", tried_skins=["orange"]
        )
        self.client.force_login(member)
        self.client.post("/ru/accounts/logout/", {"next": "/ru/news/"})
        self.assertNotContains(self.client.get("/ru/news/"), 'id="skin-offer"')
