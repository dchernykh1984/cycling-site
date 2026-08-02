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
import time
from dataclasses import dataclass
from typing import Any

from telegram_agent.channels import Channel

_MAX_MESSAGE_CHARS = 2000
# Below this a message cannot be an announcement. Measured over 1218 real messages from these six
# channels: 13% fall under this floor and not one of them is an announcement or a correction to
# one -- they are "spasibo", "krasivo", "@banofbot", a lone emoji. The floor was checked at this
# height on purpose, since dropping a real "moved to 8:00" would cost more than keeping noise:
# every message between 6 and 14 characters was read by hand, and all of it was chatter.
_MIN_MESSAGE_CHARS = 15
# How many messages one prompt carries. A long prompt is not just expensive, it is worse at the job:
# a single announcement among five hundred replies about bike lights is exactly the needle a long
# context loses. Reading ten days of a busy chat therefore becomes several prompts, not one huge one.
MESSAGES_PER_PROMPT = 100
# The longest FloodWait worth sitting out. Telegram hands out waits of a few seconds routinely when
# several channels are read in a row; a nightly, unhurried run just serves those. Anything longer
# means tonight is over for this channel, and the wait is reported instead.
_FLOOD_PATIENCE_SECONDS = 60


class ChannelUnavailableError(Exception):
    """The channel could not be read: not joined, expired invite, flood-limited, or gone."""


@dataclass(frozen=True)
class Message:
    """One channel message, as far as an event announcement is concerned."""

    text: str
    published: datetime.date


def worth_reading(text: str) -> bool:
    """Whether a message could possibly be an announcement (pure, unit-tested)."""
    return len(" ".join(text.split())) >= _MIN_MESSAGE_CHARS


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
    from telethon.tl.types import ChatInviteAlready

    try:
        if channel.ref.startswith("+"):
            answer = client(CheckChatInviteRequest(invite_hash(channel.ref)))
            if isinstance(answer, ChatInviteAlready):
                return answer.chat
            raise ChannelUnavailableError(
                "the service account has not joined this invite -- open it from the account's phone first"
            )
        if channel.ref.startswith("c/"):
            # A marked id (-100...) is passed bare: PeerChannel wants the unmarked form, and the
            # marked integer is the one Telethon resolves directly. A private channel is not in the
            # session cache until the account's dialogs have been listed once, so an unknown id
            # gets one dialog sweep before it is declared not joined.
            try:
                return client.get_entity(internal_id(channel.ref))
            except ValueError:
                client.get_dialogs()
                try:
                    return client.get_entity(internal_id(channel.ref))
                except ValueError:
                    raise ChannelUnavailableError(
                        "not among the account's chats -- join it from the account's phone first"
                    ) from None
        return client.get_entity(channel.ref)
    except (InviteHashExpiredError, InviteHashInvalidError) as exc:
        raise ChannelUnavailableError("the invite link has expired or was revoked") from exc
    except (UsernameNotOccupiedError, UsernameInvalidError) as exc:
        raise ChannelUnavailableError("no such public channel or group") from exc
    except ChannelPrivateError as exc:
        raise ChannelUnavailableError("the channel is private and the account is not in it") from exc
    except ValueError as exc:
        # Telethon wraps UsernameNotOccupiedError into a bare ValueError when resolving a string,
        # so a vanished username never reaches the except above. Measured live on a group that
        # went private and gave its username up: without this the whole error handling is dead
        # code and the log shows a raw "fetch failed" instead of the reason.
        raise ChannelUnavailableError("no such public channel or group -- the username is not in use") from exc


def _sit_out(seconds: int) -> None:
    """Serve a FloodWait if it is short, or report it if it is not (pure decision, unit-tested).

    FloodWait is Telegram saying "slower" with a number of seconds attached, and checking invites
    is one of the calls it slows readily -- so the whole read of a channel sits under this, not
    just fetching the messages.
    """
    if seconds > _FLOOD_PATIENCE_SECONDS:
        raise ChannelUnavailableError(f"Telegram asked to wait {seconds}s (flood limit)")
    time.sleep(seconds + 1)


def read_messages(client: Any, channel: Channel, recent_hours: int, max_posts: int) -> tuple[str, list[Message], bool]:
    """The channel's title, its messages from the last ``recent_hours``, and whether the cap bit.

    Coverage-omitted I/O; the decisions it makes are in :func:`worth_reading` and :func:`within`.

    Read by time, not by count, because the two are not interchangeable across these channels:
    measured here, the newest 50 messages of a busy group do not reach back a single day while 50
    of a quiet channel reach back two years. Telegram hands messages back newest first, so the read
    simply stops at the first one older than the window -- no paging arithmetic, and a quiet
    channel costs one request.

    The name rides along because the channels file carries bare ids on purpose, and a private
    channel is credited on the site by this name and nothing else.

    Both steps sit under the FloodWait envelope -- resolving an invite (CheckChatInvite) is the
    call Telegram slows most readily, not the message fetch. The entity is resolved once and kept:
    retrying the fetch must not spend a second invite check on the same channel.
    """
    from telethon.errors import FloodWaitError

    try:
        entity = entity_of(client, channel)
    except FloodWaitError as exc:
        _sit_out(exc.seconds)
        entity = entity_of(client, channel)
    try:
        messages, capped = _collect(client, entity, recent_hours, max_posts)
    except FloodWaitError as exc:
        # Served once: a second FloodWait straight after the first means Telegram is not asking for
        # patience but for absence, and the channel is reported rather than hammered.
        _sit_out(exc.seconds)
        try:
            messages, capped = _collect(client, entity, recent_hours, max_posts)
        except FloodWaitError as again:
            raise ChannelUnavailableError(f"Telegram asked to wait {again.seconds}s twice (flood limit)") from again
    return (getattr(entity, "title", "") or "").strip(), messages, capped


def _collect(client: Any, entity: Any, recent_hours: int, max_posts: int) -> tuple[list[Message], bool]:
    """Messages newer than the window, newest first, and whether the safety net stopped the read."""
    oldest_wanted = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=recent_hours)
    messages: list[Message] = []
    for item in client.iter_messages(entity):
        when = getattr(item, "date", None)
        if when is None:
            continue
        if when < oldest_wanted:
            return messages, False  # Telegram hands them back newest first: everything below is older
        text = " ".join((getattr(item, "message", "") or "").split())
        if worth_reading(text):
            messages.append(Message(text=text[:_MAX_MESSAGE_CHARS], published=when.date()))
        if max_posts and len(messages) >= max_posts:
            return messages, True
    return messages, False


def reading_note(ref: str, messages: list[Message], recent_hours: int, capped: bool) -> str:
    """One log line saying how much of the channel the run actually saw (pure, unit-tested).

    "0 extracted" alone cannot be told apart from "the run barely saw the channel" -- this line is
    what tells them apart. When the safety net stopped the read it says so outright: a silent
    truncation would read exactly like a quiet night.
    """
    if not messages:
        return f"  ~ {ref}: no messages worth reading in the last {recent_hours}h"
    note = f"  ~ {ref}: read {len(messages)} messages of the last {recent_hours}h, back to {messages[-1].published}"
    if capped:
        note += " -- CAPPED, older messages in the window were not read"
    return note


def in_batches(messages: list[Message], size: int = MESSAGES_PER_PROMPT) -> list[list[Message]]:
    """The messages split into prompt-sized batches, in the order they were written (unit-tested).

    One prompt per hundred messages rather than one prompt for everything: a long context is not
    merely expensive, it is worse at finding the single announcement buried in a day of chatter,
    and ten days of a busy group would crowd out the taxonomy and the known-events list as well.

    Telegram hands messages back newest first -- which is what the read needs, to know when to
    stop -- but that is backwards for reading a conversation: the model would meet the replies
    before the announcement they answer, and "moved to 8:00" before the ride it moves. So the
    batches are handed over oldest first, the way the chat was written.
    """
    if not messages:
        return []
    in_order = list(reversed(messages))
    return [in_order[start : start + size] for start in range(0, len(in_order), max(size, 1))]


def channel_text(channel: Channel, messages: list[Message], recent_hours: int, today: datetime.date) -> str:
    """One batch of a channel's messages as the text the model reads (pure, unit-tested).

    Every message carries the date it was published: that is what turns an announcement's "this
    Saturday" into a real date. No links are included -- an announcement in a private channel has
    no address the public could open.
    """
    # A public group is named to the model; an invite hash or internal id is not -- the model has
    # no business seeing a credential-like string it could echo into a description.
    named = channel.ref if channel.ref.startswith("@") else "(a private channel)"
    lines = [f"Telegram channel: {named}"]
    if channel.hint:
        lines.append(f"What the maintainers know about it: {channel.hint}")
    if channel.city:
        lines.append(f"This community is based in: {channel.city}")
    lines.append(f"Today is {today.isoformat()}. Messages published in the last {recent_hours} hours:")
    for message in messages:
        lines.append(f"\n--- published {message.published.isoformat()}\n{message.text}")
    return "\n".join(lines)
