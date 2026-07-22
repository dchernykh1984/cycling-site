"""Parse events_sources.yaml into fetchable Source objects.

The file groups sources by type (``aggregators`` / ``organizers`` / ``telegram_public`` /
``telegram_account`` / ``telegram_private``); each entry is a bare string (URL or @handle) or a
mapping with ``url`` plus optional ``hint`` / ``enabled``. Public Telegram channels are read through
the t.me/s/<channel> web preview (no account). ``telegram_account`` (public groups/chats or a user --
no invite, but an account) and ``telegram_private`` (t.me/+invite, t.me/c/...) cannot be read without
a logged-in account, so they are marked and the run skips and logs them.
"""

from __future__ import annotations

import re

import yaml

from agent.models import Source

_HANDLE = re.compile(r"@?([A-Za-z0-9_]{3,})")
_TME_PATH = re.compile(r"t\.me/(\S+)", re.IGNORECASE)
_URL = re.compile(r"https?://[^\s()]+", re.IGNORECASE)

# events_sources.yaml section -> Source.kind
# Sources are scanned in this order, and a run stops as soon as it has proposed its quota, so the
# order is what actually enforces guidance.md's geography ladder. Organizers and the public Telegram
# channels are the Kazakh and Kyrgyz ones; the aggregators are Russian and worldwide calendars with
# dozens of rows each, and going through them first would spend every nightly slot before a single
# local source was read. The account/private Telegram sections are unreadable and merely reported.
_SECTION_KIND = {
    "organizers": "organizer",
    "telegram_public": "tg_public",
    "aggregators": "aggregator",
    "telegram_account": "tg_account",
    "telegram_private": "tg_private",
}


def _entry_fields(entry: object) -> tuple[str, str, bool]:
    """(ref, hint, enabled) from a bare-string or mapping entry; ref is "" for a malformed entry."""
    if isinstance(entry, str):
        return entry.strip(), "", True
    if isinstance(entry, dict):
        ref = str(entry.get("url") or entry.get("ref") or "").strip()
        return ref, str(entry.get("hint") or "").strip(), bool(entry.get("enabled", True))
    return "", "", True


def _tg_channel(ref: str) -> str | None:
    """The public channel name from a t.me URL / @handle, or None for a private / unparseable ref."""
    ref = ref.strip()
    tme = _TME_PATH.search(ref)
    if tme:
        path = tme.group(1).strip("/")
        if path.startswith("s/"):  # a pasted t.me/s/<channel> web-preview URL
            path = path[2:]
        if path.startswith(("+", "c/")):
            return None  # private invite link or internal channel id -- not web-readable
        channel = path.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]  # drop /<post_id>, query, frag
        return channel or None
    match = _HANDLE.fullmatch(ref)
    return match.group(1) if match else None


def _build_source(kind: str, ref: str, hint: str) -> Source | None:
    """Build one Source, or None when the ref carries no fetchable URL / channel."""
    if kind == "tg_public":
        channel = _tg_channel(ref)
        if channel is not None:
            return Source("tg_public", ref, f"https://t.me/s/{channel}", hint=hint)
        return Source("tg_private", ref, None, hint=hint)  # an invite/internal link mis-filed as public
    if kind in ("tg_account", "tg_private"):
        return Source(kind, ref, None, hint=hint)  # public group / private chat: needs a logged-in account
    match = _URL.search(ref)
    return Source(kind, ref, match.group(0).rstrip(".,;"), hint=hint) if match else None


def parse_sources(text: str) -> list[Source]:
    """Return the de-duplicated sources declared in the events_sources.yaml text."""
    data = yaml.safe_load(text)
    if not isinstance(data, dict):  # empty file or a malformed top level (list/scalar) -> no sources
        return []
    sources: list[Source] = []
    seen: set[str] = set()

    def add(source: Source) -> None:
        key = f"{source.kind}:{source.fetch_url or source.ref.lower()}"
        if key not in seen:
            seen.add(key)
            sources.append(source)

    for section, kind in _SECTION_KIND.items():
        for entry in data.get(section) or []:
            ref, hint, enabled = _entry_fields(entry)
            if not ref or not enabled:
                continue
            source = _build_source(kind, ref, hint)
            if source is not None:
                add(source)
    return sources
