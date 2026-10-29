"""A conversation: starting one, one turn of it, and linking it to the event its form saved (issue #353)."""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from django.db import transaction

from api.auth import is_admin
from assistant import fields, llm, prompt
from assistant.models import Conversation, Message

MAX_TEXT = 10_000
_KINDS = ("route", "regulations")


def start(user, competition=None) -> tuple[Conversation, bool]:
    """The event's own conversation, or a new one for an event still being added; True when created."""
    if competition is None:
        return Conversation.objects.create(started_by=user), True
    return Conversation.objects.get_or_create(competition=competition, defaults={"started_by": user})


def _point(start) -> list[float] | None:
    try:
        lat, lng = float(start[0]), float(start[1])
    except (TypeError, ValueError, IndexError, KeyError):
        return None
    return [lat, lng] if -90 <= lat <= 90 and -180 <= lng <= 180 else None


def _attachments(items: list[dict]) -> list[dict]:
    """The files of a message, kept to the shape ``Message.attachments`` describes."""
    return [
        {"kind": item["kind"], "name": item["name"].strip()[:200], "start": _point(item.get("start"))}
        for item in items[:5]
        if item.get("kind") in _KINDS and isinstance(item.get("name"), str)
    ]


def _track_start(conversation: Conversation, attachments: list[dict]) -> tuple[float, float] | None:
    """Where the latest route the administrator attached starts."""
    earlier = [item for message in conversation.messages.filter(role=Message.Role.USER) for item in message.attachments]
    for item in reversed(earlier + attachments):
        if item.get("kind") == "route" and item.get("start"):
            return item["start"][0], item["start"][1]
    return None


@dataclass
class Turn:
    reply: str
    form: dict
    notes: list[str]
    asked: Message
    replied: Message


def take_turn(
    conversation: Conversation,
    user,
    text: str,
    *,
    form: dict,
    attachments: list[dict],
    today: datetime.date,
    language: str,
) -> Turn:
    """Ask the model; keep the administrator's message and the reply only when it answered.

    Raises ``llm.UnavailableError``: nothing is stored then, so the message can simply be sent again.
    """
    from calendar_app.views import _get_locations_data  # the views link conversations: import late

    images: list[str] = []
    current = prompt.describe_form(form, conversation.competition, images)
    attachments = _attachments(attachments)
    content = prompt.turn(text, current, attachments, today, language, editing=conversation.competition_id is not None)
    answer = llm.complete(prompt.messages(conversation, content))
    reply = answer.get("reply")
    if not isinstance(reply, str) or not reply.strip():
        raise llm.UnavailableError(llm.UnavailableError.BAD_ANSWER)
    said = [*conversation.messages.filter(role=Message.Role.USER).values_list("text", flat=True), text]
    changes = answer.get("set") or {}
    # Every place the page offers is read only when the reply names one: most turns do not.
    names_a_place = isinstance(changes, dict) and isinstance(changes.get("place"), dict)
    checked = fields.check(
        changes,
        current=current,
        texts=said,
        rows=_get_locations_data(user) if names_a_place else [],
        point=_track_start(conversation, attachments),
        images=images,
    )
    with transaction.atomic():
        asked = Message.objects.create(
            conversation=conversation, role=Message.Role.USER, author=user, text=text, attachments=attachments
        )
        replied = Message.objects.create(
            conversation=conversation, role=Message.Role.ASSISTANT, text=reply.strip(), fields=checked.set
        )
        conversation.save(update_fields=["updated_at"])
    return Turn(reply=replied.text, form=checked.form, notes=checked.notes, asked=asked, replied=replied)


def link(conversation_id, competition, user) -> bool:
    """Link a conversation to the event the form just saved; False when it is not an admin's to link."""
    if not is_admin(user) or not str(conversation_id or "").isdigit():
        return False
    if Conversation.objects.filter(competition=competition).exists():
        return False
    linked = Conversation.objects.filter(pk=int(conversation_id), competition__isnull=True).update(
        competition=competition
    )
    return linked == 1
