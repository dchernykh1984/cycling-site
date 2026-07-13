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
    event_type_id: int | None = None
    discipline_ids: list[int] = field(default_factory=list)
    # Free-text location hints from the LLM, resolved to a site location_id at create time:
    country: str = ""
    region: str = ""
    city: str = ""
    venue: str = ""  # the specific start venue / address, if the announcement gives one
    lat: float | None = None
    lng: float | None = None
    # Kazakh / English translations (the ru value lives in the base field above); the site stores
    # every event and venue name in all three locales.
    title_kk: str = ""
    title_en: str = ""
    description_kk: str = ""
    description_en: str = ""
    venue_kk: str = ""
    venue_en: str = ""


@dataclass
class Taxonomy:
    """The site's event types and disciplines, for the LLM to classify against and for validation."""

    event_types: list[dict] = field(default_factory=list)  # [{"id", "name"}]
    disciplines: list[dict] = field(default_factory=list)  # [{"id", "name", "category"}]

    @property
    def event_type_ids(self) -> set[int]:
        return {item["id"] for item in self.event_types}

    @property
    def discipline_ids(self) -> set[int]:
        return {item["id"] for item in self.disciplines}


@dataclass
class KnownEvents:
    """What the site already knows, used to avoid re-proposing.

    ``existing_keys`` covers approved + the agent's own pending events (for the pipeline's exact
    dedup); ``existing`` is the same events as readable title/date pairs, shown to the LLM so it can
    also skip near-duplicates worded differently. ``rejected`` lists the agent's past rejections
    (with reasons) so the run can both skip them and feed the reasons to the LLM as "do not propose
    things like these".
    """

    existing_keys: set[str] = field(default_factory=set)
    existing: list[dict] = field(default_factory=list)  # [{"title","date_start"}], shown to the LLM
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
