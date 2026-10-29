"""The assistant's conversations, kept with their event so that its edit page goes on where adding it stopped.

A conversation starts before its event exists: the admin adds an event by talking, and only the
form's own button saves it. The conversation is linked to the event then, and the event's edit page
continues it with everything said so far (issue #353).
"""

from typing import ClassVar

from django.conf import settings
from django.db import models


class Conversation(models.Model):
    objects: ClassVar[models.Manager["Conversation"]]

    competition = models.OneToOneField(
        "calendar_app.Competition",
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
    # A reply's changes to the form, by the form's field names.
    fields = models.JSONField(default=dict, blank=True)
    # An admin's message's files: [{"kind": "route" | "regulations", "name": ..., "start": [lat, lng] | null}].
    attachments = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar[list] = ["created_at", "pk"]

    def __str__(self) -> str:
        return f"{self.role}: {self.text[:40]}"
