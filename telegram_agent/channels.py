"""Read telegram_channels.yaml into the channels a run should visit (no I/O, unit-tested).

Three ways a Telegram place is written, all of which need a logged-in account to read:

- ``https://t.me/+HASH`` -- an invite link to a private channel or chat the service account has
  already accepted. The hash is all Telegram needs to find the chat again.
- ``https://t.me/c/<id>[/<message>]`` -- an internal link to a private channel, the form Telegram
  itself copies from inside one. The id is the channel's own; any trailing message number is noise.
- ``@handle`` or ``https://t.me/handle`` -- a public group or channel. Public, but a *group* has
  members rather than subscribers and no t.me/s/ web preview, so the account-less events agent
  cannot read it and it lives here instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import yaml

# A public username as Telegram allows it: letters, digits and underscores, five characters up.
_USERNAME = re.compile(r"^[A-Za-z0-9_]{5,32}$")
# Both invite spellings: the current t.me/+HASH and the old t.me/joinchat/HASH, which still
# circulates in pinned messages and old chat descriptions. Read as one kind -- the hash is the same.
_INVITE = re.compile(r"t\.me/(?:\+|joinchat/)([A-Za-z0-9_-]+)")
_INTERNAL = re.compile(r"t\.me/c/(\d+)")
# The same internal id written without any domain: "c/<id>", the API's marked "-100<id>", or the
# bare number, with or without topic/message tails. Domain-free is the preferred spelling here --
# t.me has gone NXDOMAIN before, and nothing about an id needs a web host.
_BARE_INTERNAL = re.compile(r"^(?:c/|-100)?(\d{6,})(?:/\d+)*$")
_PUBLIC_URL = re.compile(r"t\.me/([A-Za-z0-9_]{5,32})")


@dataclass(frozen=True)
class Channel:
    """One Telegram channel or group to read, with what the maintainers know about it."""

    ref: str  # "+HASH", "c/<id>" or "@handle" -- normalized, and how logs name it
    hint: str = ""  # free-text nudge passed to the model, like a web source's hint
    city: str = ""  # where this community is based, for announcements that never name the place


def _ref_of(value: str) -> str:
    """The normalized ref from a pasted link, an @handle or a bare username; "" if unusable."""
    text = (value or "").strip().strip("/")
    if not text:
        return ""
    invite = _INVITE.search(text)
    if invite:
        return f"+{invite.group(1)}"
    internal = _INTERNAL.search(text)
    if internal:
        return f"c/{internal.group(1)}"
    bare = _BARE_INTERNAL.match(text)
    if bare:
        return f"c/{bare.group(1)}"
    url = _PUBLIC_URL.search(text)
    if url:
        return f"@{url.group(1)}"
    name = text.removeprefix("@").split("?", 1)[0].split("/", 1)[0]
    return f"@{name}" if _USERNAME.match(name) else ""


def parse_channels(text: str) -> list[Channel]:
    """The enabled channels declared in the telegram_channels.yaml text, de-duplicated in order."""
    data = yaml.safe_load(text)
    entries = data.get("channels") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        return []
    channels: list[Channel] = []
    seen: set[str] = set()
    for entry in entries:
        if isinstance(entry, (str, int)):
            # An unquoted bare id ("- 1796089754") arrives as YAML's integer, not a string.
            ref, hint, city, enabled = _ref_of(str(entry)), "", "", True
        elif isinstance(entry, dict):
            ref = _ref_of(str(entry.get("url") or entry.get("channel") or ""))
            hint = str(entry.get("hint") or "").strip()
            city = str(entry.get("city") or "").strip()
            enabled = bool(entry.get("enabled", True))
        else:
            continue
        if not ref or not enabled or ref.lower() in seen:
            continue
        seen.add(ref.lower())
        channels.append(Channel(ref=ref, hint=hint, city=city))
    return channels


def post_link(ref: str, message_id: int, topic_id: int | None = None, chat_id: int | None = None) -> str:
    """The address of one message, as Telegram itself would copy it.

    A public channel or group has a handle, and its posts are addressed by it. A private one has
    no public address at all -- but Telegram still gives every member the internal form,
    ``t.me/c/<id>/<message>``, which is what a member pastes when they quote a post. That is the
    link this agent publishes for a private source: it opens the post for anyone in the chat, and
    shows nothing to anyone else.

    A forum's topics sit between the chat and the message (``/<topic>/<message>``); without the
    topic the link still resolves, but Telegram opens the chat rather than the post.

    Returns "" when there is nothing to build from -- an invite-hash ref whose chat id was never
    read, or a message with no number.
    """
    if not message_id:
        return ""
    if ref.startswith("@"):
        base = f"https://t.me/{ref[1:]}"
    elif ref.startswith("c/"):
        base = f"https://t.me/{ref}"
    elif chat_id:
        # An invite ref names no chat; the id read when the channel was opened does.
        base = f"https://t.me/c/{chat_id}"
    else:
        return ""
    tail = f"{topic_id}/{message_id}" if topic_id else str(message_id)
    return f"{base}/{tail}"
