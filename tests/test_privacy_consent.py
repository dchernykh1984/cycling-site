"""The privacy policy asked of every new member (issue #438): on the sign-up form, and at the first
sign-in of an account Google, GitHub or Strava made, which no form asked. Members from before the
question are never asked."""

import datetime

from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext

from accounts.adapters import SocialAccountAdapter
from accounts.models import User
from registrations.tests import make_user


def _url(name):
    with translation.override("en"):
        return reverse(name)


class SignupTests(TestCase):
    def _sign_up(self, **extra):
        data = {"email": "new@test.local", "password1": "Long-enough-9!", "password2": "Long-enough-9!", **extra}
        return self.client.post(_url("account_signup"), data)

    def test_the_form_asks_last_with_the_policy_a_tab_away(self):
        page = self.client.get(_url("account_signup"))
        form = page.context["form"]
        self.assertEqual(list(form.fields)[-1], "privacy")
        self.assertTrue(form.fields["privacy"].required)
        self.assertContains(page, f'href="{_url("privacy_policy")}" target="_blank" rel="noopener"')

    def test_under_the_box_it_says_there_is_no_account_without_the_yes(self):
        with translation.override("ru"):
            hint = gettext("Without agreeing to the privacy policy you cannot sign up.")
            page = self.client.get(reverse("account_signup"))
        self.assertContains(page, f'<span class="helptext" id="id_privacy_helptext">{hint}</span>', html=True)
        self.assertContains(page, 'aria-describedby="id_privacy_helptext"')

    def test_without_the_tick_no_account_is_made(self):
        self._sign_up()
        self.assertFalse(User.objects.filter(email="new@test.local").exists())

    def test_with_the_tick_the_account_keeps_when_it_was_given(self):
        self._sign_up(privacy="on")
        user = User.objects.get(email="new@test.local")
        self.assertIsNotNone(user.privacy_accepted_at)
        self.assertFalse(user.privacy_consent_pending)


class ProviderAccountTests(TestCase):
    def setUp(self):
        self.member = make_user("strava", first_name="Ivan", last_name="Petrov", gender="M")
        self.member.privacy_consent_pending = True
        self.member.save(update_fields=["privacy_consent_pending"])
        self.client.force_login(self.member)

    def test_a_new_account_a_provider_made_waits_for_the_answer(self):
        request = RequestFactory().get("/")
        request.user = AnonymousUser()
        request.session = self.client.session
        user = User(username="fresh", email="fresh@test.local")
        login = SocialLogin(user=user, account=SocialAccount(provider="strava", uid="42"), email_addresses=[])
        saved = SocialAccountAdapter().save_user(request, login)
        saved.refresh_from_db()
        self.assertTrue(saved.privacy_consent_pending)
        self.assertIsNone(saved.privacy_accepted_at)

    def test_every_page_sends_the_member_to_the_question_and_back_after_the_yes(self):
        page = _url("account_profile")
        answer = self.client.get(page)
        self.assertRedirects(answer, f"{_url('account_privacy_consent')}?next={page.replace('/', '%2F')}")
        question = self.client.get(answer["Location"])
        self.assertContains(question, f'href="{_url("privacy_policy")}"')
        self.assertContains(question, "Without agreeing to the privacy policy you cannot sign up.")
        self.assertContains(question, 'aria-describedby="id_privacy_helptext"')
        self.assertEqual(question.context["next"], page)
        back = self.client.post(_url("account_privacy_consent"), {"privacy": "on", "next": page})
        self.assertRedirects(back, page)
        self.member.refresh_from_db()
        self.assertFalse(self.member.privacy_consent_pending)
        self.assertIsNotNone(self.member.privacy_accepted_at)
        self.assertEqual(self.client.get(page).status_code, 200)

    def test_no_tick_no_way_on(self):
        answer = self.client.post(_url("account_privacy_consent"), {"next": _url("account_profile")})
        self.assertEqual(answer.status_code, 200)
        self.assertIn("privacy", answer.context["form"].errors)
        self.member.refresh_from_db()
        self.assertTrue(self.member.privacy_consent_pending)

    def test_another_sites_next_leads_to_the_profile_instead(self):
        back = self.client.post(_url("account_privacy_consent"), {"privacy": "on", "next": "https://evil.example/"})
        self.assertRedirects(back, _url("account_profile"))

    def test_the_policy_the_terms_signing_out_and_the_api_stay_open(self):
        for name in ("privacy_policy", "terms_of_use"):
            self.assertEqual(self.client.get(_url(name)).status_code, 200, name)
        self.assertEqual(self.client.get("/api/v1/virtual-members/").status_code, 200)
        self.client.post(_url("account_logout"))
        self.assertNotIn("_auth_user_id", self.client.session)


class ExistingMemberTests(TestCase):
    def test_a_member_from_before_the_question_is_never_asked(self):
        member = make_user("old", birth_date=datetime.date(1990, 1, 1))
        self.assertIsNone(member.privacy_accepted_at)
        self.client.force_login(member)
        self.assertEqual(self.client.get(_url("account_profile")).status_code, 200)
        self.assertRedirects(
            self.client.get(_url("account_privacy_consent"), {"next": _url("account_profile")}),
            _url("account_profile"),
        )
