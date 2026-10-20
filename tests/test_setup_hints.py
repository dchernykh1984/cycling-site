"""The setup hint at the top of the page (issue #319).

One line, never two: sign in when signed out, then -- for a member -- calendar preferences on the
calendar pages, the data a race entry needs, a second way to sign in, a Strava link. Each member's
reminder can be turned off for good, one at a time; the sign-in one cannot be closed.
"""

import datetime

from allauth.socialaccount.models import SocialAccount
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from calendar_app.models import DisciplineCategory

LIST = reverse("calendar_list")
NEWS = reverse("news_index")


def _member(**fields):
    defaults = {"username": "rider", "email": "rider@example.com", "password": "pw", "role": User.Role.PARTICIPANT}
    defaults.update(fields)
    return User.objects.create_user(**defaults)


def _complete(user, *, preferences=True, data=True, second_way=True, strava=True):
    if preferences:
        user.preferred_directions.add(DisciplineCategory.objects.create(name_ru="Road", order=1))
    if data:
        user.first_name, user.last_name = "Ivan", "Petrov"
        user.gender, user.birth_date = "M", datetime.date(1990, 1, 1)
    if strava:
        user.strava_link = "https://www.strava.com/athletes/1"
    user.save()
    if second_way:
        SocialAccount.objects.create(user=user, provider="google", uid=f"g-{user.pk}")
    return user


class SignedOutTests(TestCase):
    def test_every_page_asks_to_sign_in_and_brings_the_reader_back(self):
        for url in (LIST, NEWS):
            with self.subTest(url=url):
                response = self.client.get(url)
                hint = response.context["setup_hint"]
                self.assertEqual(hint["key"], "sign_in")
                self.assertIn("next=", hint["login_url"])
                self.assertContains(response, 'id="setup-hint"', count=1)

    def test_it_cannot_be_closed(self):
        self.assertNotContains(self.client.get(LIST), "account_dismiss_hint")
        self.assertNotContains(self.client.get(LIST), "hints/")

    def test_search_engines_do_not_quote_it(self):
        self.assertContains(self.client.get(NEWS), "data-nosnippet")

    def test_not_on_the_sign_in_page_itself(self):
        self.assertNotContains(self.client.get(reverse("account_login")), 'id="setup-hint"')

    def test_not_on_the_continue_with_a_service_step_either(self):
        """allauth names these pages after the service, so a list of route names would miss them."""
        from accounts.views import signin_providers

        providers = [pid for pid, _ in signin_providers()]
        self.assertTrue(providers, "no sign-in services configured, so nothing would be checked")
        for pid in providers:
            with self.subTest(provider=pid):
                response = self.client.get(reverse(f"{pid}_login"))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, 'id="setup-hint"')

    def test_the_next_address_survives_filters(self):
        response = self.client.get(f"{LIST}?date_from=2026-01-01&discipline=3")
        self.assertIn("date_from%3D2026-01-01%26discipline%3D3", response.context["setup_hint"]["login_url"])


class MemberOrderTests(TestCase):
    def _hint(self, user, url=LIST):
        self.client.force_login(user)
        # follow: a member with saved preferences is redirected to the calendar filtered by them.
        return (self.client.get(url, follow=True).context.get("setup_hint") or {}).get("key")

    def test_preferences_first_on_the_calendar_pages(self):
        user = _complete(_member(), preferences=False)
        for name in ("calendar", "calendar_list", "calendar_map"):
            with self.subTest(page=name):
                self.assertEqual(self._hint(user, reverse(name)), "preferences")

    def test_preferences_are_not_asked_for_elsewhere(self):
        user = _complete(_member(), preferences=False)
        self.assertIsNone(self._hint(user, NEWS))

    def test_then_the_data_a_race_entry_needs(self):
        user = _complete(_member(), data=False)
        self.assertEqual(self._hint(user), "registration_data")
        self.assertEqual(self._hint(user, NEWS), "registration_data")

    def test_then_a_second_way_to_sign_in(self):
        self.assertEqual(self._hint(_complete(_member(), second_way=False)), "signin_methods")

    def test_then_strava(self):
        self.assertEqual(self._hint(_complete(_member(), strava=False)), "strava")

    def test_nothing_once_everything_is_set(self):
        self.assertIsNone(self._hint(_complete(_member())))

    def test_only_one_at_a_time(self):
        user = _member()
        self.client.force_login(user)
        self.assertContains(self.client.get(LIST), 'id="setup-hint"', count=1)

    def test_not_on_the_profile_pages(self):
        user = _member()
        self.client.force_login(user)
        for name in ("account_profile", "account_profile_edit"):
            with self.subTest(page=name):
                self.assertNotContains(self.client.get(reverse(name)), 'id="setup-hint"')


class UnconfirmedEmailTests(TestCase):
    """Signed up but never confirmed: a guest in all but name, and that comes before anything else."""

    def setUp(self):
        self.user = _member(role=User.Role.GUEST)
        self.client.force_login(self.user)

    def test_it_comes_first_even_on_the_calendar(self):
        hint = self.client.get(LIST).context["setup_hint"]
        self.assertEqual(hint["key"], "confirm_email")
        self.assertEqual(hint["url"], reverse("account_profile"))

    def test_it_cannot_be_closed(self):
        self.assertNotContains(self.client.get(NEWS), "return confirm(")
        response = self.client.post(reverse("account_dismiss_hint", args=["confirm_email"]), {"next": NEWS})
        self.assertEqual(response.status_code, 404)

    def test_confirmed_members_never_see_it(self):
        self.client.force_login(_complete(_member(username="ok", email="ok@example.com"), preferences=False))
        self.assertEqual(self.client.get(LIST).context["setup_hint"]["key"], "preferences")


class RaceEntryFormTests(TestCase):
    def test_the_entry_form_is_left_to_say_what_is_missing_itself(self):
        from django.utils import timezone

        from calendar_app.models import Competition

        race = Competition.objects.create(
            title_ru="Race",
            date_start=timezone.localdate() + datetime.timedelta(days=5),
            status=Competition.Status.APPROVED,
            registration_enabled=True,
        )
        self.client.force_login(_member())
        response = self.client.get(reverse("registrations:register", args=[race.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="setup-hint"')


class DismissTests(TestCase):
    def setUp(self):
        self.user = _complete(_member(), preferences=False, data=False)
        self.client.force_login(self.user)

    def _dismiss(self, key, nxt=LIST):
        return self.client.post(reverse("account_dismiss_hint", args=[key]), {"next": nxt})

    def test_turning_one_off_brings_up_the_next(self):
        self.assertRedirects(self._dismiss("preferences"), LIST, fetch_redirect_response=False)
        self.assertEqual(self.client.get(LIST).context["setup_hint"]["key"], "registration_data")
        self.user.refresh_from_db()
        self.assertEqual(self.user.dismissed_hints, ["preferences"])

    def test_turning_it_off_twice_keeps_one_entry(self):
        self._dismiss("preferences")
        self._dismiss("preferences")
        self.user.refresh_from_db()
        self.assertEqual(self.user.dismissed_hints, ["preferences"])

    def test_the_sign_in_hint_is_not_dismissible(self):
        self.assertEqual(self._dismiss("sign_in").status_code, 404)

    def test_an_unknown_hint_is_not_stored(self):
        self.assertEqual(self._dismiss("anything").status_code, 404)
        self.user.refresh_from_db()
        self.assertEqual(self.user.dismissed_hints, [])

    def test_a_foreign_next_address_is_not_followed(self):
        response = self._dismiss("preferences", nxt="https://evil.example.com/")
        self.assertEqual(response["Location"], "/")

    def test_the_link_asks_before_turning_off(self):
        self.assertContains(self.client.get(LIST), "return confirm(")

    def test_signed_out_cannot_dismiss(self):
        self.client.logout()
        response = self._dismiss("preferences")
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("account_login"), response["Location"])


class TranslationTests(TestCase):
    MSGIDS = (
        "Sign in, and the calendar fits you: only your sports and your city, favourites, and entering races "
        "in one click.",
        "Choose your sports, event types and places in your profile or straight from the calendar filter, and the "
        "calendar, list and map will open with them.",
        "Add your name, gender and date of birth to your profile: race entries will be filled in for you.",
        "Your account has only one way to sign in. Add a second one, so losing it does not lock you out.",
        "Add your Strava profile link: races that ask for it will take it from your entry.",
        "Choose",
        "Fill in",
        "Do not remind me again",
        "Set the site up for yourself",
        "Stop this reminder for good? You can still change it in your profile at any time.",
        "Confirm your email address: until then you cannot enter races, add events or comment. Look for the "
        "letter in your inbox, or send it again from your profile.",
        "Confirm",
    )

    def test_every_hint_is_translated(self):
        from django.utils.translation import gettext, override

        for msgid in self.MSGIDS:
            for lang in ("ru", "kk"):
                with self.subTest(msgid=msgid[:30], lang=lang), override(lang):
                    self.assertNotEqual(gettext(msgid), msgid)
