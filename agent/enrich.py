"""Pure helpers for the second, enrichment pass (no I/O, unit-tested).

After the first pass extracts an event and the organizer's own event-page URL, a second pass may
fetch that page and re-read it to improve the event. This module decides whether a page is worth
fetching and merges the refined event onto the original, keeping the original wherever the refined
version is empty -- so a failed or partial enrichment never loses what we already had.
"""

from __future__ import annotations

from dataclasses import fields, replace
from urllib.parse import urlsplit

from agent.models import Candidate

_EMPTY: tuple[object, ...] = (None, "", [])


def should_enrich(candidate: Candidate) -> bool:
    """Whether the candidate points at a real, specific web page worth fetching for more detail."""
    url = (candidate.source_url or "").strip()
    if not url:
        return False
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return False
    return bool(parts.path.strip("/"))  # a specific page, not a bare homepage / channel root


def merge_candidate(base: Candidate, refined: Candidate) -> Candidate:
    """Overlay the refined event's non-empty fields onto ``base`` (``base`` wins where empty)."""
    updates = {f.name: getattr(refined, f.name) for f in fields(base) if getattr(refined, f.name) not in _EMPTY}
    # Keep the announcement page we enriched from rather than whatever the refine step echoed back.
    updates["source_url"] = base.source_url or refined.source_url
    return replace(base, **updates)
