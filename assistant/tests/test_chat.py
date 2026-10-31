"""The chat on the event's pages: who is offered it, what the page carries, and the link on saving."""

import json
import re

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext

from accounts.models import User
from assistant.models import Conversation, Message
from assistant.tests.helpers import competition, news, user, venue

KEY = "sk-never-in-a-page"
TOGGLE = 'id="assistant-toggle"'


CONFIG = re.compile(r'<script id="assistant-config" type="application/json">(.*?)</script>', re.S)


def _config(page) -> dict:
    found = CONFIG.search(page.content.decode())
    assert found is not None, "the page carries no chat"
    return json.loads(found.group(1))


@override_settings(ASSISTANT_LLM_API_KEY=KEY)
class ChatOnThePageTests(TestCase):
    def setUp(self):
        self.admin = user()
        self.shop = venue()

    def test_an_admin_is_offered_the_chat_and_the_page_never_holds_the_key(self):
        self.client.force_login(self.admin)
        page = self.client.get(reverse("calendar_submit"))
        self.assertContains(page, TOGGLE)
        self.assertNotContains(page, KEY)
        config = _config(page)
        self.assertEqual((config["conversationId"], config["subjectId"]), (None, None))
        self.assertEqual(config["start"], "/api/v1/assistant/conversations")

    def test_nobody_below_an_organizer_is_offered_it_and_no_site_without_a_key(self):
        self.client.force_login(user("rider", User.Role.PARTICIPANT))
        self.assertNotContains(self.client.get(reverse("calendar_submit")), TOGGLE)
        self.client.force_login(self.admin)
        with override_settings(ASSISTANT_LLM_API_KEY=""):
            self.assertNotContains(self.client.get(reverse("calendar_submit")), TOGGLE)

    def test_the_edit_page_goes_on_with_the_events_conversation(self):
        event = competition(location=self.shop, submitted_by=self.admin)
        conversation = Conversation.objects.create(competition=event)
        Message.objects.create(conversation=conversation, role=Message.Role.USER, text="Move it to Sunday")
        self.client.force_login(self.admin)
        page = self.client.get(reverse("competition_edit", args=[event.pk]))
        config = _config(page)
        self.assertEqual((config["conversationId"], config["subjectId"]), (conversation.pk, event.pk))
        self.assertContains(page, "Move it to Sunday")

    def test_saving_the_form_links_the_conversation_to_the_new_event(self):
        conversation = Conversation.objects.create(started_by=self.admin)
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("calendar_submit"),
            {
                "title_ru": "Ride",
                "date_start": "2026-11-20",
                "location": str(self.shop.pk),
                "assistant_conversation": str(conversation.pk),
            },
        )
        self.assertEqual(response.status_code, 302)
        conversation.refresh_from_db()
        self.assertEqual(conversation.competition.title_ru, "Ride")

    def test_a_refused_form_brings_its_conversation_back(self):
        conversation = Conversation.objects.create(started_by=self.admin)
        Message.objects.create(conversation=conversation, role=Message.Role.USER, text="A ride on Saturday")
        self.client.force_login(self.admin)
        page = self.client.post(reverse("calendar_submit"), {"assistant_conversation": str(conversation.pk)})
        self.assertEqual(page.status_code, 200)
        self.assertEqual(_config(page)["conversationId"], conversation.pk)
        self.assertContains(page, "A ride on Saturday")

    def test_an_organizer_is_offered_it_on_their_own_events_pages(self):
        organizer = user("org", User.Role.ORGANIZER)
        event = competition(location=self.shop, submitted_by=organizer)
        conversation = Conversation.objects.create(competition=event, started_by=organizer)
        self.client.force_login(organizer)
        self.assertEqual(_config(self.client.get(reverse("calendar_submit")))["conversationId"], None)
        config = _config(self.client.get(reverse("competition_edit", args=[event.pk])))
        self.assertEqual((config["conversationId"], config["subjectId"]), (conversation.pk, event.pk))

    def _submit(self, conversation, **extra):
        return self.client.post(reverse("calendar_submit"), {"assistant_conversation": str(conversation.pk), **extra})

    def test_an_organizer_never_gets_someone_elses_conversation(self):
        organizer = user("org", User.Role.ORGANIZER)
        others = Conversation.objects.create(started_by=self.admin)
        Message.objects.create(conversation=others, role=Message.Role.USER, text="A secret ride")
        self.client.force_login(organizer)
        refused = self._submit(others)
        self.assertEqual(_config(refused)["conversationId"], None)
        self.assertNotContains(refused, "A secret ride")
        saved = self._submit(others, title_ru="Ride", date_start="2026-11-20", location=str(self.shop.pk))
        self.assertEqual(saved.status_code, 302)
        others.refresh_from_db()
        self.assertIsNone(others.competition)

    def test_saving_an_organizers_form_links_their_own_conversation(self):
        organizer = user("org", User.Role.ORGANIZER)
        own = Conversation.objects.create(started_by=organizer)
        self.client.force_login(organizer)
        saved = self._submit(own, title_ru="Ride", date_start="2026-11-20", location=str(self.shop.pk))
        self.assertEqual(saved.status_code, 302)
        own.refresh_from_db()
        self.assertEqual((own.competition.title_ru, own.competition.submitted_by), ("Ride", organizer))

    def test_the_chat_speaks_the_pages_language(self):
        self.client.force_login(self.admin)
        config = _config(self.client.get("/kk/calendar/submit/"))
        with translation.override("kk"):
            first = gettext("What event would you like to add?")
        self.assertNotEqual(first, "What event would you like to add?")
        self.assertEqual((config["language"], config["words"]["first"]), ("kk", first))


@override_settings(ASSISTANT_LLM_API_KEY=KEY)
class NewsChatTests(TestCase):
    def setUp(self):
        self.admin = user()
        self.client.force_login(self.admin)

    def _page(self, name, *args):
        with translation.override("en"):
            return self.client.get(reverse(name, args=args))

    def test_the_news_form_offers_a_chat_of_its_own_kind(self):
        config = _config(self._page("news_article_create"))
        self.assertEqual((config["kind"], config["attach"], config["subjectId"]), ("news", False, None))
        self.assertEqual(config["editors"], {"body_ru": "quill-ru", "body_kk": "quill-kk", "body_en": "quill-en"})
        self.assertEqual(config["words"]["first"], "What news would you like to write?")

    def test_a_news_items_edit_page_goes_on_with_its_conversation(self):
        item = news()
        conversation = Conversation.objects.create(kind=Conversation.Kind.NEWS, news=item)
        Message.objects.create(conversation=conversation, role=Message.Role.USER, text="Translate it")
        page = self._page("news_article_edit", item.pk)
        config = _config(page)
        self.assertEqual((config["conversationId"], config["subjectId"]), (conversation.pk, item.pk))
        self.assertEqual(config["words"]["first"], "What would you like to change in this news item?")
        self.assertContains(page, "Translate it")

    def _save_news(self, conversation):
        return self.client.post(
            reverse("news_article_create"),
            {"title_ru": "Novost", "published_at": "2026-10-29T10:00", "assistant_conversation": str(conversation.pk)},
        )

    def test_saving_a_news_item_links_its_conversation(self):
        conversation = Conversation.objects.create(kind=Conversation.Kind.NEWS, started_by=self.admin)
        self.assertEqual(self._save_news(conversation).status_code, 302)
        conversation.refresh_from_db()
        self.assertEqual(conversation.news.title_ru, "Novost")

    def test_an_events_conversation_is_never_linked_to_a_news_item(self):
        conversation = Conversation.objects.create(kind=Conversation.Kind.EVENT, started_by=self.admin)
        self.assertEqual(self._save_news(conversation).status_code, 302)
        conversation.refresh_from_db()
        self.assertIsNone(conversation.news)


class PrivacyPolicyTests(TestCase):
    LINE = (
        "<strong>The assistant.</strong> The site's administrators may write events and news by talking to an "
        "assistant on their pages. What they write to it, and the form as it stands, go to a language-model "
        "provider, which prepares the texts; the conversation is kept on the site with its event or news item."
    )

    def test_the_policy_says_the_chat_goes_to_a_language_model_without_naming_one(self):
        for language in ("en", "ru", "kk"):
            with self.subTest(language=language), translation.override(language):
                page = self.client.get(reverse("privacy_policy"))
                self.assertContains(page, gettext(self.LINE))
                self.assertNotContains(page, "DeepSeek")
