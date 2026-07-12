"""Pure orchestration of one agent run: no network or LLM calls happen here.

The fetcher, the LLM extractor and the "create competition" call are passed in as callables, so the
whole flow -- dedup against what the site already knows, skipping past rejections, validating
candidates and capping how many are proposed -- is unit-tested with simple fakes.
"""

from __future__ import annotations

import datetime
import json
import re
from collections.abc import Callable

from agent.models import Candidate, KnownEvents, RunReport, Source, Taxonomy

# Callables the runner injects (real versions live in fetch.py / llm.py / site_api.py).
FetchFn = Callable[[Source], str]
ExtractFn = Callable[[str, Source], list[Candidate]]
CreateFn = Callable[[Candidate], None]

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def normalize_key(title: str, date_start: str) -> str:
    """A dedup key: lower-cased, punctuation-stripped title + start date."""
    norm = _PUNCT.sub("", (title or "").lower())
    norm = _WS.sub(" ", norm).strip()
    return f"{norm}|{(date_start or '').strip()}"


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def _localized(value: object) -> tuple[str, str, str]:
    """(ru, kk, en) from a {"ru","kk","en"} dict, or a plain string treated as the ru value."""
    if isinstance(value, dict):
        return (
            str(value.get("ru") or "").strip(),
            str(value.get("kk") or "").strip(),
            str(value.get("en") or "").strip(),
        )
    return str(value or "").strip(), "", ""


def _as_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def parse_candidates(raw: str, source_url: str = "", taxonomy: Taxonomy | None = None) -> list[Candidate]:
    """Parse the LLM's reply into candidates, tolerating code fences and stray prose.

    Expects a JSON array of objects with title/date_start (and optional date_end/description/
    source_url/event_type_id/discipline_ids). Anything malformed is skipped rather than raising, so
    one bad item never sinks a run. When ``taxonomy`` is given, a hallucinated event type or
    discipline id (not on the site) is dropped rather than sent and rejected.
    """
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []
    try:
        items = json.loads(text[start : end + 1])
    except (ValueError, TypeError):
        return []
    candidates: list[Candidate] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        title_ru, title_kk, title_en = _localized(item.get("title"))
        date_start = str(item.get("date_start") or "").strip()
        if not title_ru or not date_start:
            continue
        event_type_id = _as_int(item.get("event_type_id"))
        raw_disciplines = item.get("discipline_ids")
        if not isinstance(raw_disciplines, list):
            raw_disciplines = []
        discipline_ids = [d for d in (_as_int(x) for x in raw_disciplines) if d is not None]
        if taxonomy is not None:
            if event_type_id not in taxonomy.event_type_ids:
                event_type_id = None
            discipline_ids = [d for d in discipline_ids if d in taxonomy.discipline_ids]
        desc_ru, desc_kk, desc_en = _localized(item.get("description"))
        venue_ru, venue_kk, venue_en = _localized(item.get("venue"))
        candidates.append(
            Candidate(
                title=title_ru[:255],
                date_start=date_start,
                date_end=(str(item.get("date_end")).strip() or None) if item.get("date_end") else None,
                description=desc_ru,
                source_url=str(item.get("source_url") or source_url).strip(),
                event_type_id=event_type_id,
                discipline_ids=discipline_ids,
                country=str(item.get("country") or "").strip(),
                region=str(item.get("region") or "").strip(),
                city=str(item.get("city") or "").strip(),
                venue=venue_ru,
                lat=_as_float(item.get("lat")),
                lng=_as_float(item.get("lng")),
                title_kk=title_kk[:255],
                title_en=title_en[:255],
                description_kk=desc_kk,
                description_en=desc_en,
                venue_kk=venue_kk,
                venue_en=venue_en,
            )
        )
    return candidates


def _is_valid(candidate: Candidate, today: datetime.date) -> tuple[bool, str]:
    """Whether a candidate is worth proposing (valid future date); returns (ok, reason)."""
    try:
        start = datetime.date.fromisoformat(candidate.date_start)
    except ValueError:
        return False, "bad date"
    if start < today:
        return False, "past event"
    if candidate.date_end:
        try:
            if datetime.date.fromisoformat(candidate.date_end) < start:
                return False, "end before start"
        except ValueError:
            return False, "bad end date"
    return True, ""


def _source_candidates(source: Source, fetch: FetchFn, extract: ExtractFn, report: RunReport) -> list[Candidate]:
    """Fetch + extract one source's candidates; log and return [] on an unsupported source or error."""
    if source.kind == "tg_private" or not source.fetch_url:
        report.skipped_sources.append((source.ref, "private/unsupported source"))
        return []
    try:
        text = fetch(source)
    except Exception as exc:
        report.skipped_sources.append((source.ref, f"fetch failed: {exc}"))
        return []
    try:
        return extract(text, source)
    except Exception as exc:
        report.skipped_sources.append((source.ref, f"extract failed: {exc}"))
        return []


def _consider(
    candidate: Candidate, seen: set[str], report: RunReport, today: datetime.date, *, create: CreateFn, dry_run: bool
) -> None:
    """Dedup + validate one candidate; accept (and post, unless dry-run) or record why it was skipped."""
    key = normalize_key(candidate.title, candidate.date_start)
    if key in seen:
        report.skipped_candidates.append((candidate.title, "already known or rejected"))
        return
    ok, reason = _is_valid(candidate, today)
    if not ok:
        report.skipped_candidates.append((candidate.title, reason))
        return
    seen.add(key)
    report.accepted.append(candidate)
    if not dry_run:
        try:
            create(candidate)
        except Exception as exc:
            report.post_errors.append((candidate.title, str(exc)))


def run_pipeline(
    sources: list[Source],
    known: KnownEvents,
    *,
    fetch: FetchFn,
    extract: ExtractFn,
    create: CreateFn,
    max_events: int,
    dry_run: bool,
    today: datetime.date | None = None,
) -> RunReport:
    """Fetch each source, extract candidates, and propose new valid ones up to ``max_events``."""
    today = today or datetime.date.today()
    report = RunReport(dry_run=dry_run)
    # Never re-propose something already on the site or previously rejected.
    seen = set(known.existing_keys) | {r["key"] for r in known.rejected}

    for source in sources:
        if report.capped:
            break
        for candidate in _source_candidates(source, fetch, extract, report):
            if len(report.accepted) >= max_events:
                report.capped = True
                break
            _consider(candidate, seen, report, today, create=create, dry_run=dry_run)
    return report
