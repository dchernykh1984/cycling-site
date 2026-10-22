"""The account pages stay out of search; the reader-facing pages around them do not."""

from django.test import TestCase


class AccountPagesNoindexTests(TestCase):
    def test_sign_in_sign_up_and_password_reset_are_not_indexed(self):
        for path in ("/ru/accounts/login/", "/kk/accounts/signup/", "/en/accounts/password/reset/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["X-Robots-Tag"], "noindex")

    def test_the_rest_of_the_site_is(self):
        for path in ("/ru/", "/ru/news/", "/ru/calendar/list/"):
            with self.subTest(path=path):
                self.assertNotIn("X-Robots-Tag", self.client.get(path))
