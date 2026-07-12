"""Plain data structures shared across the agent (no I/O, so they are easy to unit-test)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Source:
    """One place to look for events. ``fetch_url`` is None for sources we cannot read yet."""

    kind: str  # "website" | "tg_public" | "tg_private"
    ref: str  # the original line/URL from events_sources.txt (for logging)
    fetch_url: str | None = None  # normalized URL the fetcher should GET


@dataclass
class Candidate:
    """An event the LLM proposes from a source's text."""

    title: str
    date_start: str  # ISO YYYY-MM-DD
    date_end: str | None = None
    description: str = ""
    source_url: str = ""


@dataclass
class KnownEvents:
    """What the site already knows, used to avoid re-proposing.

    ``existing_keys`` covers approved + the agent's own pending events; ``rejected`` lists the
    agent's past rejections (with reasons) so the run can both skip them and feed the reasons to
    the LLM as "do not propose things like these".
    """

    existing_keys: set[str] = field(default_factory=set)
    rejected: list[dict] = field(default_factory=list)  # [{"key","title","date_start","reason"}]


@dataclass
class RunReport:
    """Summary of one run, for logging and assertions."""

    accepted: list[Candidate] = field(default_factory=list)  # passed all checks (posted or dry-run)
    skipped_candidates: list[tuple[str, str]] = field(default_factory=list)  # (title, reason)
    skipped_sources: list[tuple[str, str]] = field(default_factory=list)  # (ref, reason)
    post_errors: list[tuple[str, str]] = field(default_factory=list)  # (title, error)
    capped: bool = False
    dry_run: bool = False
