"""The share button beside a page's heading (issue #327).

On every public page. An event's own page decides what it hands out: its address when anybody can
open it; its invitation link for an invite-only event, and then only to the people who may edit it.
A link that would open for nobody it is sent to -- a hidden or not-yet-approved event, an invitee
passing on a plain address -- gets no button at all.
"""

import datetime
import re

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from calendar_app.models import Competition, CompetitionInvite
from news.models import NewsArticle

BUTTON = 'class="btn btn-sm btn-outline-secondary share-btn'


def _user(name, role):
    return User.objects.create_user(username=name, email=f"{name}@example.com", password="pw", role=role)


def _event(**kwargs):
    defaults = {
        "title_ru": "Race",
        "date_start": timezone.localdate() + datetime.timedelta(days=5),
        "status": Competition.Status.APPROVED,
    }
    defaults.update(kwargs)
    return Competition.objects.create(**defaults)


def _shared_url(html):
    m = re.search(r'share-btn[^>]*data-share-url="([^"]+)"', html, re.S)
    return m.group(1) if m else None


class EventPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = _user("author", User.Role.ORGANIZER)
        cls.admin = _user("admin", User.Role.ADMIN)
        cls.invitee = _user("invitee", User.Role.PARTICIPANT)

    def _page(self, event, user=None):
        if user:
            self.client.force_login(user)
        return self.client.get(reverse("competition_detail", args=[event.pk])).content.decode()

    def test_a_public_event_shares_its_own_address(self):
        event = _event(submitted_by=self.author)
        url = _shared_url(self._page(event))
        self.assertTrue(url.startswith("http"), url)
        self.assertTrue(url.endswith(reverse("competition_detail", args=[event.pk])), url)

    def test_an_invite_only_event_shares_its_invitation_link_with_its_editors(self):
        event = _event(submitted_by=self.author, invite_only=True)
        link = reverse("competition_invite", args=[event.pk, event.invite_key])
        for user in (self.author, self.admin):
            with self.subTest(user=user.username):
                self.assertTrue(_shared_url(self._page(event, user)).endswith(link))

    def test_an_invitee_gets_no_button(self):
        event = _event(submitted_by=self.author, invite_only=True)
        CompetitionInvite.objects.create(competition=event, user=self.invitee)
        self.assertNotIn(BUTTON, self._page(event, self.invitee))

    def test_a_hidden_event_gets_no_button_even_for_its_editor(self):
        self.assertNotIn(BUTTON, self._page(_event(submitted_by=self.author, is_hidden=True), self.author))

    def test_an_event_awaiting_review_gets_no_button(self):
        event = _event(submitted_by=self.author, status=Competition.Status.PENDING_APPROVAL)
        self.assertNotIn(BUTTON, self._page(event, self.author))


class PublicPagesTests(TestCase):
    def test_the_calendar_list_and_map_carry_it(self):
        for name in ("calendar", "calendar_list", "calendar_map"):
            with self.subTest(page=name):
                self.assertContains(self.client.get(reverse(name)), BUTTON)

    def test_the_calendar_list_and_map_build_the_link_from_the_filters(self):
        for name in ("calendar", "calendar_list", "calendar_map"):
            with self.subTest(page=name):
                self.assertContains(self.client.get(reverse(name)), "window.shareUrl = function")

    def test_news_list_search_and_the_legal_pages_carry_it(self):
        for name in ("news_index", "search", "privacy_policy", "terms_of_use"):
            with self.subTest(page=name):
                self.assertContains(self.client.get(reverse(name)), BUTTON)

    def test_a_news_article_carries_it_unless_it_is_hidden(self):
        editor = User.objects.create_superuser(username="boss", email="boss@example.com", password="pw")
        self.client.force_login(editor)
        shown = NewsArticle.objects.create(title_ru="Shown", body_ru="<p>x</p>")
        hidden = NewsArticle.objects.create(title_ru="Hidden", body_ru="<p>x</p>", is_hidden=True)
        self.assertContains(self.client.get(shown.get_absolute_url()), BUTTON)
        self.assertNotContains(self.client.get(hidden.get_absolute_url()), BUTTON)

    def test_the_participant_list_carries_it_only_for_a_public_event(self):
        public = _event()
        self.assertContains(self.client.get(reverse("registrations:participant_list", args=[public.pk])), BUTTON)
        private = _event(invite_only=True)
        admin = _user("adm", User.Role.ADMIN)
        self.client.force_login(admin)
        response = self.client.get(reverse("registrations:participant_list", args=[private.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, BUTTON)

    def test_not_on_personal_pages(self):
        self.client.force_login(_user("me", User.Role.PARTICIPANT))
        for name in ("account_profile", "account_profile_edit", "calendar_submit"):
            with self.subTest(page=name):
                self.assertNotContains(self.client.get(reverse(name)), BUTTON)
