"""The header's "Log in" leads back to the page it was pressed on.

It led to the home page, so a reader who signed in to enter a race had to find the race again.
"""

import datetime
from urllib.parse import quote

from allauth.account.models import EmailAddress
from django.test import TestCase

from accounts.models import User
from calendar_app.models import Competition


class SignInLinkTests(TestCase):
    def setUp(self):
        self.event = Competition.objects.create(
            title_ru="Race", date_start=datetime.date(2027, 5, 1), status=Competition.Status.APPROVED
        )

    def _link(self, page):
        return f'href="/ru/accounts/login/?next={quote(page, safe="")}"'

    def test_the_link_names_the_page_it_is_on_with_its_filters(self):
        for page in (f"/ru/calendar/{self.event.pk}/", "/ru/calendar/list/?period=weekend&location=1"):
            with self.subTest(page=page):
                html = self.client.get(page).content.decode()
                self.assertIn(self._link(page).replace("&", "&amp;"), html)

    def test_an_account_page_sends_no_page_back(self):
        html = self.client.get("/ru/accounts/signup/").content.decode()
        self.assertIn('href="/ru/accounts/login/"', html)
        self.assertNotIn("/ru/accounts/login/?next=", html)

    def test_signing_in_from_the_link_returns_to_the_page(self):
        user = User.objects.create_user(
            username="rider", email="rider@example.com", password="Pass-12345!", role=User.Role.PARTICIPANT
        )
        EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
        page = f"/ru/calendar/{self.event.pk}/"
        response = self.client.post(
            f"/ru/accounts/login/?next={quote(page, safe='')}", {"login": user.email, "password": "Pass-12345!"}
        )
        self.assertEqual(response["Location"], page)
