"""A turn of a conversation, and linking a conversation to the event its form saved."""

import datetime
from unittest import mock

from django.test import TestCase, override_settings

from accounts.models import User
from assistant import conversations
from assistant.models import Conversation, Message
from assistant.tests.helpers import city, competition, user, venue


def _turn(conversation, admin, text, **extra):
    options = {"form": {}, "attachments": [], "today": datetime.date(2026, 10, 29), "language": "ru", **extra}
    return conversations.take_turn(conversation, admin, text, **options)


@override_settings(ASSISTANT_LLM_API_KEY="sk-test")
class TurnTests(TestCase):
    def setUp(self):
        self.admin = user()
        self.town = city()

    def test_a_track_attached_earlier_places_a_new_venue_later(self):
        conversation, _ = conversations.start(self.admin)
        with mock.patch("assistant.llm.complete", return_value={"reply": "Got the track.", "set": {}}):
            _turn(
                conversation,
                self.admin,
                "ride.gpx",
                attachments=[{"kind": "route", "name": "ride.gpx", "start": [43.25, 76.95]}],
            )
        answer = {"reply": "Noted.", "set": {"place": {"city": "Testville", "venue": {"ru": "Vkhod v park"}}}}
        with mock.patch("assistant.llm.complete", return_value=answer) as complete:
            turn = _turn(conversation, self.admin, "Start at the park entrance")
        self.assertEqual((turn.form["new_venue"]["lat"], turn.form["new_venue"]["lng"]), (43.25, 76.95))
        history = complete.call_args.args[0]
        self.assertIn("The track starts at 43.250000, 76.950000.", history[1]["content"])

    def test_the_sites_places_are_read_only_when_a_reply_names_one(self):
        conversation, _ = conversations.start(self.admin)
        place = {"city": "Testville", "venue": {"ru": "Most"}}
        with mock.patch("calendar_app.views._get_locations_data", return_value=[]) as read:
            with mock.patch("assistant.llm.complete", return_value={"reply": "When?", "set": {"title": {"ru": "X"}}}):
                _turn(conversation, self.admin, "A ride")
            self.assertEqual(read.call_count, 0)
            with mock.patch("assistant.llm.complete", return_value={"reply": "Noted.", "set": {"place": place}}):
                _turn(conversation, self.admin, "From the bridge")
            self.assertEqual(read.call_count, 1)

    def test_an_attachment_is_kept_to_its_shape(self):
        conversation, _ = conversations.start(self.admin)
        attachments = [
            {"kind": "route", "name": " a.gpx ", "start": ["x", 1]},
            {"kind": "photo", "name": "b.jpg"},
            {"kind": "regulations", "name": "rules.pdf", "start": [100, 0]},
        ]
        with mock.patch("assistant.llm.complete", return_value={"reply": "Ok.", "set": {}}):
            turn = _turn(conversation, self.admin, "files", attachments=attachments)
        self.assertEqual(
            turn.asked.attachments,
            [
                {"kind": "route", "name": "a.gpx", "start": None},
                {"kind": "regulations", "name": "rules.pdf", "start": None},
            ],
        )

    def test_an_events_conversation_is_told_it_edits(self):
        event = competition(location=venue(self.town))
        conversation, created = conversations.start(self.admin, event)
        self.assertTrue(created)
        with mock.patch("assistant.llm.complete", return_value={"reply": "What changes?", "set": {}}) as complete:
            _turn(conversation, self.admin, "Move it a day later")
        self.assertIn("editing an event already on the site", complete.call_args.args[0][-1]["content"])


class LinkTests(TestCase):
    def setUp(self):
        self.admin = user()
        self.event = competition()

    def test_an_admins_new_conversation_is_linked_to_the_saved_event(self):
        conversation, _ = conversations.start(self.admin)
        self.assertTrue(conversations.link(str(conversation.pk), self.event, self.admin))
        conversation.refresh_from_db()
        self.assertEqual(conversation.competition, self.event)

    def test_nothing_is_linked_for_a_non_admin_a_taken_event_or_a_bad_id(self):
        organizer = user("org", User.Role.ORGANIZER)
        conversation, _ = conversations.start(self.admin)
        self.assertFalse(conversations.link(conversation.pk, self.event, organizer))
        self.assertFalse(conversations.link("abc", self.event, self.admin))
        self.assertFalse(conversations.link(None, self.event, self.admin))
        Conversation.objects.create(competition=self.event)
        self.assertFalse(conversations.link(conversation.pk, self.event, self.admin))
        self.assertFalse(Message.objects.exists())
