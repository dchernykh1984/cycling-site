"""Read a Telegram channel's recent messages through the service account. Network I/O in the
client-touching functions, which are coverage-omitted; the pure parts are unit-tested.

This is the MTProto client API (Telethon), not the Bot API, and that is the point of the whole
agent: a bot sees only chats an admin added it to, while these sources are other people's private
channels and public *groups* -- readable only by a member account. The service account joins each
channel once, by hand, from a phone; a run then only reads. Nothing is ever sent, nothing is
joined automatically -- automatic joining is exactly the pattern Telegram's anti-spam is built to
catch, and the account is the one thing this agent cannot afford to lose.

Telethon is imported lazily inside the functions that need it: the tests and the site's own CI
exercise the pure parts and never need the dependency installed.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any

from telegram_agent.channels import Channel

_MAX_MESSAGE_CHARS = 2000


class ChannelUnavailableError(Exception):
    """The channel could not be read: not joined, expired invite, flood-limited, or gone."""


@dataclass(frozen=True)
class Message:
    """One channel message, as far as an event announcement is concerned."""

    text: str
    published: datetime.date


def invite_hash(ref: str) -> str:
    """The bare hash of an invite ref ("+HASH"), which is how Telegram is asked about it."""
    return ref.removeprefix("+")


def internal_id(ref: str) -> int:
    """The real channel id behind a t.me/c/<id> ref.

    Telegram's internal links carry the bare id; the API addresses the same channel as
    -100<id> -- a convention, not arithmetic, so it is string concatenation on purpose.
    """
    return int("-100" + ref.removeprefix("c/"))


def open_client(api_id: int, api_hash: str, session: str) -> Any:
    """A connected, authorized Telethon client for the service account. Coverage-omitted I/O."""
    from telethon.sessions import StringSession
    from telethon.sync import TelegramClient

    client = TelegramClient(StringSession(session), api_id, api_hash)
    client.connect()
    if not client.is_user_authorized():
        client.disconnect()
        raise ChannelUnavailableError(
            "the Telegram session is not authorized -- it was revoked or never logged in; "
            "mint a new TELEGRAM_SESSION locally and update the secret"
        )
    return client


def entity_of(client: Any, channel: Channel) -> Any:
    """The Telegram entity a channel ref names. Coverage-omitted I/O.

    An invite link is resolved through the invite itself: for a chat the account has already
    joined, Telegram answers with the chat; for one it has not, with a preview -- which is reported
    as "join it first" rather than acted on, because this agent never joins anything.
    """
    from telethon.errors import (
        ChannelPrivateError,
        InviteHashExpiredError,
        InviteHashInvalidError,
        UsernameInvalidError,
        UsernameNotOccupiedError,
    )
    from telethon.tl.functions.messages import CheckChatInviteRequest
    from telethon.tl.types import ChatInviteAlready, PeerChannel

    try:
        if channel.ref.startswith("+"):
            answer = client(CheckChatInviteRequest(invite_hash(channel.ref)))
            if isinstance(answer, ChatInviteAlready):
                return answer.chat
            raise ChannelUnavailableError(
                "the service account has not joined this invite -- open it from the account's phone first"
            )
        if channel.ref.startswith("c/"):
            return client.get_entity(PeerChannel(internal_id(channel.ref)))
        return client.get_entity(channel.ref)
    except (InviteHashExpiredError, InviteHashInvalidError) as exc:
        raise ChannelUnavailableError("the invite link has expired or was revoked") from exc
    except (UsernameNotOccupiedError, UsernameInvalidError) as exc:
        raise ChannelUnavailableError("no such public channel or group") from exc
    except ChannelPrivateError as exc:
        raise ChannelUnavailableError("the channel is private and the account is not in it") from exc


def read_messages(client: Any, channel: Channel, max_posts: int) -> list[Message]:
    """The channel's newest text messages, newest first. Coverage-omitted I/O.

    FloodWait is Telegram saying "slower" with a number of seconds attached. A short one is worth
    sitting out -- the run is nightly and unhurried; a long one means tonight is over for this
    channel, and the wait is reported instead of served.
    """
    from telethon.errors import FloodWaitError

    entity = entity_of(client, channel)
    try:
        raw = client.get_messages(entity, limit=max_posts)
    except FloodWaitError as exc:
        raise ChannelUnavailableError(f"Telegram asked to wait {exc.seconds}s (flood limit)") from exc
    messages = []
    for item in raw:
        text = (getattr(item, "message", "") or "").strip()
        when = getattr(item, "date", None)
        if text and when is not None:
            messages.append(Message(text=text[:_MAX_MESSAGE_CHARS], published=when.date()))
    return messages


def channel_text(channel: Channel, messages: list[Message], recent_days: int, today: datetime.date) -> str:
    """The channel's recent messages as the text the model reads (pure, unit-tested).

    Every message carries the date it was published: that is what turns an announcement's "this
    Saturday" into a real date. No links are included -- an announcement in a private channel has
    no address the public could open.
    """
    lines = [f"Telegram channel: {channel.ref}"]
    if channel.hint:
        lines.append(f"What the maintainers know about it: {channel.hint}")
    if channel.city:
        lines.append(f"This community rides in: {channel.city}")
    lines.append(f"Today is {today.isoformat()}. Messages published in the last {recent_days} days:")
    for message in messages:
        if (today - message.published).days > recent_days:
            continue
        lines.append(f"\n--- published {message.published.isoformat()}\n{' '.join(message.text.split())}")
    return "\n".join(lines)
