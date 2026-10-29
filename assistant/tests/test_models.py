"""A conversation lives with its event, and reads in the order it was written."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from assistant.models import Conversation, Message
from assistant.tests.helpers import competition, news, user
from calendar_app.models import Competition


class ConversationTests(TestCase):
    def test_a_conversation_goes_when_its_event_is_deleted(self):
        event = competition()
        conversation = Conversation.objects.create(competition=event, started_by=user())
        Message.objects.create(conversation=conversation, role=Message.Role.USER, text="A ride on Saturday")
        Competition.objects.filter(pk=event.pk).delete()
        self.assertFalse(Conversation.objects.exists())
        self.assertFalse(Message.objects.exists())

    def test_messages_read_in_the_order_they_were_written(self):
        conversation = Conversation.objects.create(started_by=user())
        for text in ("first", "second", "third"):
            Message.objects.create(conversation=conversation, role=Message.Role.USER, text=text)
        self.assertEqual([m.text for m in conversation.messages.all()], ["first", "second", "third"])

    def test_a_conversation_is_about_an_event_or_a_news_item_never_both(self):
        event, item = competition(), news()
        for wrong in (
            {"kind": Conversation.Kind.EVENT, "news": item},
            {"kind": Conversation.Kind.NEWS, "competition": event},
        ):
            with self.subTest(kind=str(wrong["kind"])), self.assertRaises(IntegrityError), transaction.atomic():
                Conversation.objects.create(**wrong)
        Conversation.objects.create(kind=Conversation.Kind.NEWS, news=item)
