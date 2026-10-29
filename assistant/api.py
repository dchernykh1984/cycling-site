"""The assistant's operations under /api/v1/assistant/, for admins and the owner (constitution VII).

The chat on the event's pages calls these with the site's session; a program calls them with a
personal token. What the chat does, a program can do the same way (issue #353).
"""

from __future__ import annotations

import datetime
from typing import Literal

from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from ninja import File, Router, Schema, Status
from ninja.errors import HttpError
from ninja.files import UploadedFile
from pydantic import Field

from agent.geo import parse_start
from api.auth import is_admin, member_auth
from assistant import conversations, llm
from assistant.models import Conversation
from calendar_app.models import Competition
from news.models import NewsArticle

router = Router(tags=["assistant"])

_MAX_TRACK_BYTES = 20_000_000
_UNAVAILABLE = {
    llm.UnavailableError.NO_KEY: _("The assistant is not set up on this site."),
    llm.UnavailableError.NO_BALANCE: _(
        "The assistant's account with the model's provider is out of money. Tell the site's owner."
    ),
    llm.UnavailableError.KEY_REFUSED: _("The model's provider refused the site's key. Tell the site's owner."),
    llm.UnavailableError.BUSY: _("The model did not answer. Send the message again in a minute."),
    llm.UnavailableError.BAD_ANSWER: _("The model's answer could not be read. Send the message again."),
    llm.UnavailableError.TOO_LONG: _("The answer would be too long: ask for one language, or one part, at a time."),
}


class MessageOut(Schema):
    id: int
    role: str
    text: str
    author_id: int | None
    fields: dict
    attachments: list
    created_at: datetime.datetime


class ConversationOut(Schema):
    id: int
    kind: str
    competition_id: int | None
    news_id: int | None
    messages: list[MessageOut]


class ConversationIn(Schema):
    """An event's or a news item's own conversation by its id, or a new one of ``kind`` for one still being written."""

    kind: Literal["event", "news"] = "event"
    competition_id: int | None = None
    news_id: int | None = None


class LinkIn(Schema):
    competition_id: int | None = None
    news_id: int | None = None


class AttachmentIn(Schema):
    kind: Literal["route", "regulations"]
    name: str = Field(max_length=200)
    start: tuple[float, float] | None = None


class TurnIn(Schema):
    text: str = Field(min_length=1, max_length=conversations.MAX_TEXT)
    form: dict = Field(default_factory=dict)
    today: datetime.date | None = None
    language: Literal["ru", "kk", "en"] = "ru"
    attachments: list[AttachmentIn] = Field(default_factory=list, max_length=5)


class TurnOut(Schema):
    reply: str
    fields: dict
    notes: list[str]
    messages: list[MessageOut]


class PointOut(Schema):
    lat: float
    lng: float


def _admin(request):
    if not is_admin(request.auth):
        raise HttpError(403, "Admin role is required")
    return request.auth


def _conversation(conversation_id: int) -> Conversation:
    conversation = Conversation.objects.select_related("competition").filter(pk=conversation_id).first()
    if conversation is None:
        raise HttpError(404, "No such conversation")
    return conversation


def _subject(competition_id: int | None, news_id: int | None) -> Competition | NewsArticle | None:
    """The event or the news item a request names, or None when it names neither."""
    if competition_id is not None and news_id is not None:
        raise HttpError(422, "An event or a news item, not both")
    if competition_id is not None:
        competition = Competition.objects.filter(pk=competition_id, is_deleted=False).first()
        if competition is None:
            raise HttpError(404, "No such event")
        return competition
    if news_id is not None:
        article = NewsArticle.objects.filter(pk=news_id, is_deleted=False).first()
        if article is None:
            raise HttpError(404, "No such news item")
        return article
    return None


def _out(conversation: Conversation) -> dict:
    return {
        "id": conversation.pk,
        "kind": conversation.kind,
        "competition_id": conversation.competition_id,
        "news_id": conversation.news_id,
        "messages": list(conversation.messages.all()),
    }


@router.post(
    "/conversations",
    response={200: ConversationOut, 201: ConversationOut},
    auth=member_auth,
    summary="Start a conversation, or get an event's or a news item's own (admin)",
)
def start_conversation(request, payload: ConversationIn):
    user = _admin(request)
    subject = _subject(payload.competition_id, payload.news_id)
    conversation, created = conversations.start(user, subject, payload.kind)
    return Status(201 if created else 200, _out(conversation))


@router.get(
    "/conversations/{conversation_id}",
    response=ConversationOut,
    auth=member_auth,
    summary="A conversation and its messages (admin)",
)
def get_conversation(request, conversation_id: int):
    _admin(request)
    return _out(_conversation(conversation_id))


@router.post(
    "/conversations/{conversation_id}/messages",
    response=TurnOut,
    auth=member_auth,
    summary="Say something to the assistant and get its reply and the form's new values (admin)",
)
def send_message(request, conversation_id: int, payload: TurnIn):
    user = _admin(request)
    conversation = _conversation(conversation_id)
    text = payload.text.strip()
    if not text:
        raise HttpError(422, "The message is empty")
    with translation.override(payload.language):
        try:
            turn = conversations.take_turn(
                conversation,
                user,
                text,
                form=payload.form,
                attachments=[item.model_dump() for item in payload.attachments],
                today=payload.today or timezone.localdate(),
                language=payload.language,
            )
        except llm.UnavailableError as exc:
            raise HttpError(503, str(_UNAVAILABLE[exc.reason])) from None
    return {"reply": turn.reply, "fields": turn.form, "notes": turn.notes, "messages": [turn.asked, turn.replied]}


@router.patch(
    "/conversations/{conversation_id}",
    response=ConversationOut,
    auth=member_auth,
    summary="Link a conversation to the event or news item it wrote (admin)",
)
def link_conversation(request, conversation_id: int, payload: LinkIn):
    user = _admin(request)
    conversation = _conversation(conversation_id)
    subject = _subject(payload.competition_id, payload.news_id)
    if subject is None:
        raise HttpError(422, "Name the event or the news item")
    field, _kind = conversations.subject_field(subject)
    already = getattr(conversation, f"{field}_id") == subject.pk
    if not already and not conversations.link(conversation.pk, subject, user):
        raise HttpError(409, "The conversation or its subject is linked already, or they are of different kinds")
    conversation.refresh_from_db()
    return _out(conversation)


@router.post(
    "/track-start",
    response=PointOut,
    auth=member_auth,
    summary="Where a GPX or KML track starts (admin)",
)
def track_start(request, file: UploadedFile = File(...)):  # noqa: B008
    _admin(request)
    if file.size is None or file.size > _MAX_TRACK_BYTES:
        raise HttpError(422, "The file is too large for a track")
    point = parse_start(file.read().decode("utf-8", errors="replace"))
    if point is None:
        raise HttpError(422, "No track point was found in this file")
    return {"lat": point[0], "lng": point[1]}
