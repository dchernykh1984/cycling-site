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
_INVITE = re.compile(r"t\.me/\+([A-Za-z0-9_-]+)")
_INTERNAL = re.compile(r"t\.me/c/(\d+)")
_PUBLIC_URL = re.compile(r"t\.me/([A-Za-z0-9_]{5,32})")


@dataclass(frozen=True)
class Channel:
    """One Telegram channel or group to read, with what the maintainers know about it."""

    ref: str  # "+HASH", "c/<id>" or "@handle" -- normalized, and how logs name it
    hint: str = ""  # free-text nudge passed to the model, like a web source's hint
    city: str = ""  # where this community rides, for announcements that never name the place


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
    url = _PUBLIC_URL.search(text)
    if url:
        return f"@{url.group(1)}"
    name = text.removeprefix("@").split("?", 1)[0].split("/", 1)[0]
    return f"@{name}" if _USERNAME.match(name) else ""


def link_of(ref: str) -> str:
    """The t.me address a ref names. A real address, though not a publicly readable one."""
    if ref.startswith("@"):
        return f"https://t.me/{ref.removeprefix('@')}"
    return f"https://t.me/{ref}"


def parse_channels(text: str) -> list[Channel]:
    """The enabled channels declared in the telegram_channels.yaml text, de-duplicated in order."""
    data = yaml.safe_load(text)
    entries = data.get("channels") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        return []
    channels: list[Channel] = []
    seen: set[str] = set()
    for entry in entries:
        if isinstance(entry, str):
            ref, hint, city, enabled = _ref_of(entry), "", "", True
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
