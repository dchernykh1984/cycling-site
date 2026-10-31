"""Only organizers and up reach the model, through every door the assistant has; an organizer only
their own events and conversations, and only admins and up the news.

The key spends the maintainer's money (decisions 17 and 27), so every operation is tried as every
kind of visitor: the model is asked only for an organizer, an admin, the owner or a superuser, and
nothing is kept or linked for anyone else.
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
class OnlyOrganizersAndUpReachTheModelTests(TestCase):
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

    def test_below_organizer_every_door_is_shut_by_token_and_by_session(self):
        with mock.patch("assistant.llm.complete", return_value=REPLY) as complete:
            self.assertEqual(set(self._every_operation(self.client, {})), {401})
            for role in (User.Role.GUEST, User.Role.PARTICIPANT):
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


@override_settings(ASSISTANT_LLM_API_KEY="sk-test")
class AnOrganizerReachesOnlyTheirOwnTests(TestCase):
    def setUp(self):
        self.organizer = user("org", User.Role.ORGANIZER)
        self.other = user("other", User.Role.ORGANIZER)
        self.own_event = competition(submitted_by=self.organizer)
        self.as_json = {"content_type": "application/json", **_bearer(self.organizer)}

    def test_an_organizer_writes_their_own_event_through_every_door(self):
        with mock.patch("assistant.llm.complete", return_value=REPLY) as complete:
            started = self.client.post(f"{API}/conversations", {}, **self.as_json)
            url = f"{API}/conversations/{started.json()['id']}"
            codes = [
                started.status_code,
                self.client.post(f"{url}/messages", {"text": "A ride"}, **self.as_json).status_code,
                self.client.get(url, **_bearer(self.organizer)).status_code,
                self.client.patch(url, {"competition_id": self.own_event.pk}, **self.as_json).status_code,
                self.client.post(
                    f"{API}/track-start", {"file": SimpleUploadedFile("a.gpx", GPX)}, **_bearer(self.organizer)
                ).status_code,
            ]
            own = self.client.post(f"{API}/conversations", {"competition_id": self.own_event.pk}, **self.as_json)
        self.assertEqual(codes, [201, 200, 200, 200, 200])
        self.assertEqual((own.status_code, own.json()["id"]), (200, started.json()["id"]))
        complete.assert_called_once()

    def test_what_is_out_of_their_reach_is_a_404_and_starting_on_a_news_item_a_403(self):
        others_event = competition(submitted_by=self.other, location=self.own_event.location)
        # Another's event's, another's draft, and a news item's -- even one they started.
        out_of_reach = [
            Conversation.objects.create(competition=others_event, started_by=self.other),
            Conversation.objects.create(started_by=self.other),
            Conversation.objects.create(kind=Conversation.Kind.NEWS, started_by=self.organizer),
        ]
        own_draft = Conversation.objects.create(started_by=self.organizer)
        bearer = _bearer(self.organizer)
        with mock.patch("assistant.llm.complete", return_value=REPLY) as complete:
            for conversation in out_of_reach:
                url = f"{API}/conversations/{conversation.pk}"
                with self.subTest(conversation=conversation.pk):
                    self.assertEqual(self.client.get(url, **bearer).status_code, 404)
                    sent = self.client.post(f"{url}/messages", {"text": "A ride"}, **self.as_json)
                    self.assertEqual(sent.status_code, 404)
                    linked = self.client.patch(url, {"competition_id": self.own_event.pk}, **self.as_json)
                    self.assertEqual(linked.status_code, 404)
            started = self.client.post(f"{API}/conversations", {"competition_id": others_event.pk}, **self.as_json)
            self.assertEqual(started.status_code, 404)
            moved = self.client.patch(
                f"{API}/conversations/{own_draft.pk}", {"competition_id": others_event.pk}, **self.as_json
            )
            self.assertEqual(moved.status_code, 404)
            for body in ({"kind": "news"}, {"news_id": news().pk}):
                with self.subTest(body=body):
                    self.assertEqual(self.client.post(f"{API}/conversations", body, **self.as_json).status_code, 403)
        complete.assert_not_called()
        self.assertFalse(Message.objects.exists())
        self.assertEqual(Conversation.objects.count(), 4)
        self.assertEqual(
            list(Conversation.objects.order_by("pk").values_list("competition_id", flat=True)),
            [others_event.pk, None, None, None],
        )
