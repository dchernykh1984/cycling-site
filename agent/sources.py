"""Parse events_sources.txt into fetchable Source objects.

The file is free-form: one source per line, except a ``telegram:`` line that lists several handles.
Each line may contain website URLs, t.me links and/or @handles. Public Telegram channels are read
through the t.me/s/<channel> web preview (no account); private ones (t.me/+invite, t.me/c/...)
cannot be read without an account and are marked so the run can skip and log them.
"""

from __future__ import annotations

import re

from agent.models import Source

_URL = re.compile(r"https?://[^\s()]+", re.IGNORECASE)
_HANDLE = re.compile(r"@([A-Za-z0-9_]{3,})")
_TME_PATH = re.compile(r"t\.me/(\S+)", re.IGNORECASE)


def _telegram_source(path: str, ref: str) -> Source:
    """Classify a t.me path: +invite / c/<id> are private; otherwise a public channel."""
    path = path.strip().strip("/")
    if path.startswith("+") or path.startswith("c/"):
        return Source("tg_private", ref)
    channel = path.split("/", 1)[0]  # drop any /<post_id>
    return Source("tg_public", ref, f"https://t.me/s/{channel}")


def parse_sources(text: str) -> list[Source]:
    """Return de-duplicated sources found in the events_sources.txt text."""
    sources: list[Source] = []
    seen: set[str] = set()

    def add(source: Source) -> None:
        key = f"{source.kind}:{source.fetch_url or source.ref.lower()}"
        if key not in seen:
            seen.add(key)
            sources.append(source)

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        for match in _URL.finditer(line):
            url = match.group(0).rstrip(".,;")
            tme = _TME_PATH.search(url)
            add(_telegram_source(tme.group(1), line) if tme else Source("website", line, url))
        for match in _HANDLE.finditer(line):
            add(Source("tg_public", line, f"https://t.me/s/{match.group(1)}"))
    return sources
