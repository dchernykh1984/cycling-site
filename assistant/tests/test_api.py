"""/api/v1/assistant/ (issue #353): the chat's operations, for admins and the owner only."""

import json
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import translation
from django.utils.translation import gettext

from accounts.models import User
from api.tests import ApiTestMixin
from assistant import llm
from assistant.models import Conversation, Message
from assistant.tests.helpers import city, competition, news, user, venue

API = "/api/v1/assistant"
KEY = "sk-never-shown"
GPX = b'<?xml version="1.0"?><gpx><trk><trkseg><trkpt lat="43.2389" lon="76.9453"/></trkseg></trk></gpx>'


@override_settings(ASSISTANT_LLM_API_KEY=KEY)
class AssistantApiTests(ApiTestMixin, TestCase):
    def setUp(self):
        self.admin = user()
        self.town = city()
        self.shop = venue(self.town)

    def _start(self, **payload):
        return self.post(f"{API}/conversations", payload, self.admin)

    def _say(self, conversation_id, text="A coffee ride on Saturday", **extra):
        body = {"text": text, "form": {}, "today": "2026-10-29", "language": "en", **extra}
        return self.post(f"{API}/conversations/{conversation_id}/messages", body, self.admin)

    def test_only_admins_and_the_owner_may_use_it(self):
        for role in (User.Role.PARTICIPANT, User.Role.ORGANIZER):
            other = user(f"u-{role}", role)
            with self.subTest(role=str(role)):
                self.assertEqual(self.post(f"{API}/conversations", {}, other).status_code, 403)
        self.assertEqual(self.client.post(f"{API}/conversations", {}, content_type="application/json").status_code, 401)
        owner = user("owner", User.Role.OWNER)
        self.assertEqual(self.post(f"{API}/conversations", {}, owner).status_code, 201)

    def test_the_sites_session_is_enough(self):
        self.client.force_login(self.admin)
        response = self.client.post(f"{API}/conversations", {}, content_type="application/json")
        self.assertEqual(response.status_code, 201)

    def test_an_event_keeps_one_conversation(self):
        event = competition(location=self.shop)
        first = self._start(competition_id=event.pk)
        again = self._start(competition_id=event.pk)
        self.assertEqual((first.status_code, again.status_code), (201, 200))
        self.assertEqual(first.json()["id"], again.json()["id"])
        self.assertEqual(first.json()["competition_id"], event.pk)
        self.assertEqual(self._start(competition_id=999999).status_code, 404)

    def test_a_turn_returns_the_reply_the_forms_values_and_the_notes(self):
        conversation_id = self._start().json()["id"]
        answer = {
            "reply": "Where does it start?",
            "set": {
                "title": {"ru": "Kofe-raid", "kk": "Kofe-raid", "en": "Coffee ride"},
                "url_route": "https://strava.com/routes/1",
                "url_registration": "https://made.up/register",
                "place": {"city": "Testville", "venue": {"en": "Giant shop, Abay 47"}},
            },
        }
        with mock.patch("assistant.llm.complete", return_value=answer) as complete:
            response = self._say(conversation_id, text="Coffee ride, track https://strava.com/routes/1")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["reply"], "Where does it start?")
        self.assertEqual(body["fields"]["title_en"], "Coffee ride")
        self.assertEqual(body["fields"]["url_route"], "https://strava.com/routes/1")
        self.assertEqual(body["fields"]["location"], self.shop.pk)
        self.assertEqual(
            body["notes"],
            ["A link that is in neither your messages nor the form was left out: https://made.up/register"],
        )
        self.assertEqual([m["role"] for m in body["messages"]], ["user", "assistant"])
        sent = complete.call_args.args[0]
        self.assertEqual(sent[0]["role"], "system")
        self.assertIn("The page's language: en.", sent[-1]["content"])
        stored = Conversation.objects.get(pk=conversation_id).messages.all()
        self.assertEqual([m.text for m in stored], ["Coffee ride, track https://strava.com/routes/1", body["reply"]])
        self.assertNotIn("url_registration", stored[1].fields)

    def test_the_conversation_reads_back_in_order(self):
        conversation_id = self._start().json()["id"]
        with mock.patch("assistant.llm.complete", return_value={"reply": "When?", "set": {}}):
            self._say(conversation_id, text="A ride")
        body = self.get(f"{API}/conversations/{conversation_id}", self.admin).json()
        self.assertEqual(
            [(m["role"], m["text"]) for m in body["messages"]], [("user", "A ride"), ("assistant", "When?")]
        )

    def test_when_the_model_cannot_answer_nothing_is_kept_and_the_reason_is_given(self):
        conversation_id = self._start().json()["id"]
        no_money = llm.UnavailableError(llm.UnavailableError.NO_BALANCE)
        with mock.patch("assistant.llm.complete", side_effect=no_money):
            response = self._say(conversation_id)
        self.assertEqual(response.status_code, 503)
        self.assertIn("out of money", response.json()["detail"])
        with mock.patch("assistant.llm.complete", return_value={"reply": "  ", "set": {}}):
            self.assertEqual(self._say(conversation_id).status_code, 503)
        self.assertFalse(Message.objects.exists())

    def test_a_message_has_a_length_limit(self):
        conversation_id = self._start().json()["id"]
        self.assertEqual(self._say(conversation_id, text="x" * 10_001).status_code, 422)
        self.assertEqual(self._say(conversation_id, text="").status_code, 422)
        self.assertEqual(self._say(conversation_id, text="  \n ").status_code, 422)
        self.assertFalse(Message.objects.exists())

    def test_a_conversation_is_linked_to_the_event_it_added_once(self):
        event = competition(location=self.shop)
        conversation_id = self._start().json()["id"]
        linked = self.patch(f"{API}/conversations/{conversation_id}", {"competition_id": event.pk}, self.admin)
        self.assertEqual((linked.status_code, linked.json()["competition_id"]), (200, event.pk))
        again = self.patch(f"{API}/conversations/{conversation_id}", {"competition_id": event.pk}, self.admin)
        self.assertEqual(again.status_code, 200)
        other_id = self._start().json()["id"]
        taken = self.patch(f"{API}/conversations/{other_id}", {"competition_id": event.pk}, self.admin)
        self.assertEqual(taken.status_code, 409)

    def test_a_tracks_start_is_read_from_the_file(self):
        url = f"{API}/track-start"
        response = self.client.post(url, {"file": SimpleUploadedFile("ride.gpx", GPX)}, **self.auth(self.admin))
        self.assertEqual(response.json(), {"lat": 43.2389, "lng": 76.9453})
        not_a_track = self.client.post(url, {"file": SimpleUploadedFile("a.gpx", b"hello")}, **self.auth(self.admin))
        self.assertEqual(not_a_track.status_code, 422)

    def test_no_answer_carries_the_key(self):
        conversation_id = self._start().json()["id"]
        with mock.patch("assistant.llm.complete", return_value={"reply": "When?", "set": {}}):
            bodies = [
                self._say(conversation_id).content,
                self.get(f"{API}/conversations/{conversation_id}", self.admin).content,
            ]
        with mock.patch("assistant.llm.complete", side_effect=llm.UnavailableError(llm.UnavailableError.KEY_REFUSED)):
            bodies.append(self._say(conversation_id).content)
        for body in bodies:
            self.assertNotIn(KEY, body.decode())
        self.assertIn("refused", json.loads(bodies[-1])["detail"])

    def test_the_notes_come_in_the_pages_language(self):
        conversation_id = self._start().json()["id"]
        answer = {"reply": "Ok.", "set": {"url_route": "https://made.up/route"}}
        with mock.patch("assistant.llm.complete", return_value=answer):
            body = self._say(conversation_id, language="kk").json()
        with translation.override("kk"):
            expected = gettext("A link that is in neither your messages nor the form was left out: %(url)s")
        self.assertNotIn("A link", expected)
        self.assertEqual(body["notes"], [expected % {"url": "https://made.up/route"}])


@override_settings(ASSISTANT_LLM_API_KEY=KEY)
class NewsApiTests(ApiTestMixin, TestCase):
    def setUp(self):
        self.admin = user()
        self.item = news()

    def test_a_news_items_conversation_is_its_own_and_of_its_kind(self):
        first = self.post(f"{API}/conversations", {"news_id": self.item.pk}, self.admin)
        again = self.post(f"{API}/conversations", {"news_id": self.item.pk}, self.admin)
        self.assertEqual((first.status_code, again.status_code), (201, 200))
        self.assertEqual(first.json()["id"], again.json()["id"])
        self.assertEqual((first.json()["kind"], first.json()["news_id"]), ("news", self.item.pk))
        fresh = self.post(f"{API}/conversations", {"kind": "news"}, self.admin).json()
        self.assertEqual((fresh["kind"], fresh["news_id"]), ("news", None))

    def test_naming_both_or_a_missing_news_item_is_refused(self):
        event = competition()
        both = self.post(f"{API}/conversations", {"news_id": self.item.pk, "competition_id": event.pk}, self.admin)
        self.assertEqual(both.status_code, 422)
        self.assertEqual(self.post(f"{API}/conversations", {"news_id": 999999}, self.admin).status_code, 404)

    def test_a_news_conversation_links_to_a_news_item_and_never_to_an_event(self):
        conversation_id = self.post(f"{API}/conversations", {"kind": "news"}, self.admin).json()["id"]
        url = f"{API}/conversations/{conversation_id}"
        self.assertEqual(self.patch(url, {"competition_id": competition().pk}, self.admin).status_code, 409)
        self.assertEqual(self.patch(url, {}, self.admin).status_code, 422)
        linked = self.patch(url, {"news_id": self.item.pk}, self.admin)
        self.assertEqual((linked.status_code, linked.json()["news_id"]), (200, self.item.pk))
