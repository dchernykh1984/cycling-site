"""The assistant's conversations, kept with their event or news item so that its edit page goes on.

A conversation starts before its subject exists: the admin adds an event or writes a news item by
talking, and only the form's own button saves it. The conversation is linked to it then, and the
edit page continues it with everything said so far (issue #353).
"""

from typing import ClassVar

from django.conf import settings
from django.db import models


class Conversation(models.Model):
    objects: ClassVar[models.Manager["Conversation"]]

    class Kind(models.TextChoices):
        EVENT = "event", "Event"
        NEWS = "news", "News"

    # What the conversation is about: it decides the skills, the reply's contract and the form.
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.EVENT)
    competition = models.OneToOneField(
        "calendar_app.Competition",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="assistant_conversation",
    )
    news = models.OneToOneField(
        "news.NewsArticle",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="assistant_conversation",
    )
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints: ClassVar[list] = [
            # An event's conversation has no news item, and a news item's no event.
            models.CheckConstraint(
                condition=(models.Q(kind="event") & models.Q(news__isnull=True))
                | (models.Q(kind="news") & models.Q(competition__isnull=True)),
                name="assistant_conversation_one_subject",
            ),
        ]

    def __str__(self) -> str:
        return f"Conversation #{self.pk}"


class Message(models.Model):
    objects: ClassVar[models.Manager["Message"]]

    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=Role.choices)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    text = models.TextField()
    # A reply's changes to the form, as the model wrote them once checked (assistant/fields.py).
    fields = models.JSONField(default=dict, blank=True)
    # An admin's message's files: [{"kind": "route" | "regulations", "name": ..., "start": [lat, lng] | null}].
    attachments = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar[list] = ["created_at", "pk"]

    def __str__(self) -> str:
        return f"{self.role}: {self.text[:40]}"
