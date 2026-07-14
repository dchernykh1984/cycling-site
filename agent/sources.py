"""Parse events_sources.yaml into fetchable Source objects.

The file groups sources by type (``aggregators`` / ``organizers`` / ``telegram_public`` /
``telegram_private``); each entry is a bare string (URL or @handle) or a mapping with ``url`` plus
optional ``hint`` / ``enabled``. Public Telegram channels are read through the t.me/s/<channel> web
preview (no account); private ones (t.me/+invite, t.me/c/...) cannot be read without an account and
are marked so the run can skip and log them.
"""

from __future__ import annotations

import re

import yaml

from agent.models import Source

_HANDLE = re.compile(r"@?([A-Za-z0-9_]{3,})")
_TME_PATH = re.compile(r"t\.me/(\S+)", re.IGNORECASE)
_URL = re.compile(r"https?://[^\s()]+", re.IGNORECASE)

# events_sources.yaml section -> Source.kind
_SECTION_KIND = {
    "aggregators": "aggregator",
    "organizers": "organizer",
    "telegram_public": "tg_public",
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
    if kind in ("tg_public", "tg_private"):
        channel = _tg_channel(ref)
        if kind == "tg_private" or channel is None:
            return Source("tg_private", ref, None, hint=hint)
        return Source("tg_public", ref, f"https://t.me/s/{channel}", hint=hint)
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
