"""Both admins sign in through the site's own sign-in, which holds every attempt to allauth's limits; their
own forms took passwords without any limit."""

from urllib.parse import parse_qs, urlsplit

from django.test import TestCase

from accounts.models import User

PASSWORD = "a long pass phrase 2026"


class AdminSignInTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin", email="admin@example.com", password=PASSWORD, role=User.Role.ADMIN, is_staff=True
        )

    def assert_sent_to_the_sites_sign_in(self, response, back_to):
        self.assertEqual(response.status_code, 302)
        address = urlsplit(response["Location"])
        self.assertTrue(address.path.endswith("/accounts/login/"), response["Location"])
        self.assertEqual(parse_qs(address.query)["next"], [back_to])

    def test_both_admins_send_their_sign_in_to_the_sites(self):
        for page, home in (("/admin/login/", "/admin/"), ("/django-admin/login/", "/django-admin/")):
            with self.subTest(page=page):
                self.assert_sent_to_the_sites_sign_in(self.client.get(page), home)
                self.assert_sent_to_the_sites_sign_in(self.client.get(f"{page}?next={home}pages/"), f"{home}pages/")

    def test_a_password_sent_to_an_admins_own_form_signs_nobody_in(self):
        for page in ("/admin/login/", "/django-admin/login/"):
            with self.subTest(page=page):
                response = self.client.post(page, {"username": "admin@example.com", "password": PASSWORD})
                self.assertEqual(response.status_code, 302)
                self.assertNotIn("_auth_user_id", self.client.session)

    def test_an_admin_page_sends_a_guest_to_the_sites_sign_in(self):
        self.assert_sent_to_the_sites_sign_in(self.client.get("/admin/"), "/admin/")

    def test_signed_in_on_the_site_an_admin_reaches_the_admin(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/admin/").status_code, 200)
