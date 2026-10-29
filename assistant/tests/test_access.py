"""Only admins, the owner and a superuser reach the model, through every door the assistant has.

The key spends the maintainer's money (decision 17), so every operation is tried as every kind of
visitor: the model is asked only for an admin, the owner or a superuser, and nothing is kept or
linked for anyone else.
"""

import uuid
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from accounts.models import User
from assistant.models import Conversation, Message
from assistant.tests.helpers import competition, news, user

API = "/api/v1/assistant"
GPX = b'<gpx><trk><trkseg><trkpt lat="43.2" lon="76.9"/></trkseg></trk></gpx>'
REPLY = {"reply": "When is it?", "set": {}}


def _bearer(person) -> dict:
    return {"HTTP_AUTHORIZATION": f"Bearer {person.api_token}"}


@override_settings(ASSISTANT_LLM_API_KEY="sk-test")
class OnlyAdminsReachTheModelTests(TestCase):
    def setUp(self):
        self.conversation = Conversation.objects.create()
        self.event = competition()
        self.item = news()

    def _every_operation(self, client: Client, headers: dict) -> list[int]:
        url = f"{API}/conversations/{self.conversation.pk}"
        as_json = {"content_type": "application/json", **headers}
        return [
            client.post(f"{API}/conversations", {}, **as_json).status_code,
            client.post(f"{API}/conversations", {"news_id": self.item.pk}, **as_json).status_code,
            client.get(url, **headers).status_code,
            client.post(f"{url}/messages", {"text": "A ride"}, **as_json).status_code,
            client.patch(url, {"competition_id": self.event.pk}, **as_json).status_code,
            client.post(f"{API}/track-start", {"file": SimpleUploadedFile("a.gpx", GPX)}, **headers).status_code,
        ]

    def _nothing_happened(self, complete) -> None:
        complete.assert_not_called()
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertFalse(Message.objects.exists())
        self.conversation.refresh_from_db()
        self.assertIsNone(self.conversation.competition_id)

    def test_below_admin_every_door_is_shut_by_token_and_by_session(self):
        with mock.patch("assistant.llm.complete", return_value=REPLY) as complete:
            self.assertEqual(set(self._every_operation(self.client, {})), {401})
            for role in (User.Role.GUEST, User.Role.PARTICIPANT, User.Role.ORGANIZER):
                person = user(f"u-{role}", role)
                with self.subTest(role=str(role), by="token"):
                    self.assertEqual(set(self._every_operation(Client(), _bearer(person))), {403})
                browser = Client()
                browser.force_login(person)
                with self.subTest(role=str(role), by="session"):
                    # A guest -- an address not yet confirmed -- is not even signed in for the API.
                    expected = {401} if role == User.Role.GUEST else {403}
                    self.assertEqual(set(self._every_operation(browser, {})), expected)
        self._nothing_happened(complete)

    def test_an_inactive_admins_token_is_refused(self):
        admin = user("gone")
        admin.is_active = False
        admin.save(update_fields=["is_active"])
        with mock.patch("assistant.llm.complete", return_value=REPLY) as complete:
            self.assertEqual(set(self._every_operation(Client(), _bearer(admin))), {401})
        self._nothing_happened(complete)

    def test_an_admin_the_owner_and_a_superuser_reach_the_model(self):
        root = User.objects.create_superuser("root", "root@example.com", "pw")
        root.api_token = uuid.uuid4()
        root.save(update_fields=["api_token"])
        people = [user("admin"), user("owner", User.Role.OWNER), root]
        with mock.patch("assistant.llm.complete", return_value=REPLY) as complete:
            for person in people:
                conversation = Conversation.objects.create()
                response = self.client.post(
                    f"{API}/conversations/{conversation.pk}/messages",
                    {"text": "A ride"},
                    content_type="application/json",
                    **_bearer(person),
                )
                with self.subTest(person=person.username):
                    self.assertEqual(response.status_code, 200)
        self.assertEqual(complete.call_count, 3)

    def test_the_sites_session_needs_the_pages_csrf_token(self):
        admin = user()
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(admin)
        url = f"{API}/conversations/{self.conversation.pk}/messages"
        with mock.patch("assistant.llm.complete", return_value=REPLY) as complete:
            forged = browser.post(url, {"text": "A ride"}, content_type="application/json")
            self.assertIn(forged.status_code, (401, 403))
            complete.assert_not_called()
            browser.get("/en/calendar/submit/")
            token = browser.cookies["csrftoken"].value
            sent = browser.post(url, {"text": "A ride"}, content_type="application/json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(sent.status_code, 200)
        complete.assert_called_once()
