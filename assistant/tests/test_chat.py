"""The chat on the event's pages: who is offered it, what the page carries, and the link on saving."""

import json
import re

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext

from accounts.models import User
from assistant.models import Conversation, Message
from assistant.tests.helpers import competition, user, venue

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
        self.assertEqual((config["conversationId"], config["competitionId"]), (None, None))
        self.assertEqual(config["start"], "/api/v1/assistant/conversations")

    def test_nobody_else_is_offered_it_and_no_site_without_a_key(self):
        self.client.force_login(user("org", User.Role.ORGANIZER))
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
        self.assertEqual((config["conversationId"], config["competitionId"]), (conversation.pk, event.pk))
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

    def test_the_chat_speaks_the_pages_language(self):
        self.client.force_login(self.admin)
        config = _config(self.client.get("/kk/calendar/submit/"))
        with translation.override("kk"):
            first = gettext("What event would you like to add?")
        self.assertNotEqual(first, "What event would you like to add?")
        self.assertEqual((config["language"], config["words"]["first"]), ("kk", first))
