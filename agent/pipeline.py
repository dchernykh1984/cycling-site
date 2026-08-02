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

from agent import dedup
from agent.models import Candidate, KnownEvents, RunReport, Source, Taxonomy

# Callables the runner injects (real versions live in fetch.py / llm.py / site_api.py).
FetchFn = Callable[[Source], str]
ExtractFn = Callable[[str, Source], list[Candidate]]
EnrichFn = Callable[[Candidate], Candidate]
CreateFn = Callable[[Candidate], None]
# Which city of the site a candidate starts in, when it can be told: the third signal duplicate
# detection uses, alongside the title and the date.
CityFn = Callable[[Candidate], "int | None"]


def _no_city(candidate: Candidate) -> int | None:
    """Default resolver: no city known, so the place never rules a duplicate in or out."""
    return None


def _identity(candidate: Candidate) -> Candidate:
    return candidate


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


def _load_array_prefix(text: str, start: int) -> list:
    """Every complete JSON object in the array opening at ``start``, tolerating a truncated tail.

    The model caps its reply at its output-token limit, so a long list (a dense calendar) comes back
    cut off mid-object with no closing ``]``. json.loads of the whole thing would reject it and lose
    every event; decoding object by object salvages all the ones that serialized and stops at the
    broken tail. A well-formed reply decodes exactly as before.
    """
    decoder = json.JSONDecoder()
    items: list = []
    i, n = start + 1, len(text)
    while i < n:
        while i < n and text[i] in " \t\r\n,":
            i += 1
        if i >= n or text[i] == "]":
            break
        try:
            obj, i = decoder.raw_decode(text, i)
        except ValueError:
            break  # a truncated or malformed tail object -- keep whatever parsed cleanly before it
        items.append(obj)
    return items


def parse_candidates(raw: str, source_url: str = "", taxonomy: Taxonomy | None = None) -> list[Candidate]:
    """Parse the LLM's reply into candidates, tolerating code fences, stray prose and truncation.

    Expects a JSON array of objects with title/date_start (and optional date_end/description/
    source_url/event_type_id/discipline_ids). Anything malformed is skipped rather than raising, so
    one bad item never sinks a run, and a reply cut off at the token limit still yields the events
    that came through whole. When ``taxonomy`` is given, a hallucinated event type or discipline id
    (not on the site) is dropped rather than sent and rejected.
    """
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
    start = text.find("[")
    if start == -1:
        return []
    items = _load_array_prefix(text, start)
    candidates: list[Candidate] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title_ru, title_kk, title_en = _localized(item.get("title"))
        # A foreign race often comes back titled only in English (e.g. "Reykjavik Marathon") with an
        # empty ru field. title_ru gates the drop below and is the display fallback for the other
        # locales, so backfill it from en/kk rather than silently losing a real event for want of a
        # Russian name; en and kk keep whatever the model gave.
        title_ru = title_ru or title_en or title_kk
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
        # Region/city arrive localized too now; older/looser answers may still be a bare string.
        region_ru, region_kk, region_en = _localized(item.get("region"))
        city_ru, city_kk, city_en = _localized(item.get("city"))
        candidates.append(
            Candidate(
                title=title_ru[:255],
                date_start=date_start,
                date_end=(str(item.get("date_end")).strip() or None) if item.get("date_end") else None,
                description=desc_ru,
                source_url=str(item.get("source_url") or source_url).strip(),
                url_route=str(item.get("url_route") or "").strip(),
                url_registration=str(item.get("url_registration") or "").strip(),
                event_type_id=event_type_id,
                discipline_ids=discipline_ids,
                country=str(item.get("country") or "").strip(),
                region=region_ru,
                city=city_ru,
                venue=venue_ru,
                lat=_as_float(item.get("lat")),
                lng=_as_float(item.get("lng")),
                title_kk=title_kk[:255],
                title_en=title_en[:255],
                description_kk=desc_kk,
                description_en=desc_en,
                venue_kk=venue_kk,
                venue_en=venue_en,
                region_kk=region_kk,
                region_en=region_en,
                city_kk=city_kk,
                city_en=city_en,
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
    if not source.fetch_url:
        reason = {
            "tg_account": "needs a Telegram account -- list it in telegram_channels.yaml (Telegram agent)",
            "tg_private": "private Telegram -- list it in telegram_channels.yaml (Telegram agent)",
        }.get(source.kind, "unsupported source")
        report.skipped_sources.append((source.ref, reason))
        return []
    try:
        text = fetch(source)
    except Exception as exc:
        report.skipped_sources.append((source.ref, f"fetch failed: {exc}"))
        return []
    try:
        candidates = extract(text, source)
    except Exception as exc:
        report.skipped_sources.append((source.ref, f"extract failed: {exc}"))
        return []
    report.extracted.append((source.ref, len(candidates)))
    return candidates


def _consider(
    candidate: Candidate,
    seen: set[str],
    index: dedup.KnownIndex,
    report: RunReport,
    today: datetime.date,
    *,
    enrich: EnrichFn,
    create: CreateFn,
    dry_run: bool,
    city_of: CityFn,
) -> None:
    """Dedup + validate one candidate; accept (and post, unless dry-run) or record why it was skipped."""
    key = normalize_key(candidate.title, candidate.date_start)
    if key in seen:
        report.skipped_candidates.append((candidate.title, "already known or rejected"))
        return
    variants = [candidate.title, candidate.title_kk, candidate.title_en]
    # Name what it matched: a wrong match drops a real event silently, and an anonymous
    # "near-duplicate" gives a reader no way to notice that it was wrong.
    match = dedup.matching_known(variants, candidate.date_start, city_of(candidate), index)
    if match:
        report.skipped_candidates.append((candidate.title, f"near-duplicate of {match!r}"))
        return
    ok, reason = _is_valid(candidate, today)
    if not ok:
        report.skipped_candidates.append((candidate.title, reason))
        return
    # Second pass: fetch the event's own page and refine it (a no-op / fallback for the fake in tests).
    candidate = enrich(candidate)
    ok, reason = _is_valid(candidate, today)
    if not ok:
        report.skipped_candidates.append((candidate.title, f"after enrich: {reason}"))
        return
    seen.add(normalize_key(candidate.title, candidate.date_start))
    variants = [v for v in (candidate.title, candidate.title_kk, candidate.title_en) if v]
    # Feed it back, so a later source in this same run does not propose the same event again.
    index.add(
        {
            "title": candidate.title,
            "titles": variants,
            "date_start": candidate.date_start,
            "city_id": city_of(candidate),
        }
    )
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
    enrich: EnrichFn = _identity,
    max_per_source: int = 0,
    city_of: CityFn = _no_city,
) -> RunReport:
    """Fetch each source, extract candidates, and propose new valid ones up to ``max_events``.

    ``max_per_source`` (0 = no limit) caps what one source may contribute. Sources are not equal in
    supply: the site's own organizers run out of unseen races once they have been harvested, while a
    calendar of foreign events never does, so without a per-source cap the whole run ends up coming
    from the deepest source regardless of how relevant it is.
    """
    today = today or datetime.date.today()
    report = RunReport(dry_run=dry_run)
    # Never re-propose something already on the site or previously rejected (exact match)...
    seen = set(known.existing_keys) | {r["key"] for r in known.rejected}
    # ...and catch near-duplicates worded differently, via title words + date + city (agent.dedup).
    # The index grows as the run accepts events, so one run cannot propose the same race twice.
    index = dedup.build_index((*known.existing, *known.rejected))

    for source in sources:
        if report.capped:
            break
        from_source = 0
        for candidate in _source_candidates(source, fetch, extract, report):
            if len(report.accepted) >= max_events:
                report.capped = True
                break
            if max_per_source and from_source >= max_per_source:
                report.source_capped.append(source.ref)
                break
            before = len(report.accepted)
            _consider(
                candidate,
                seen,
                index,
                report,
                today,
                enrich=enrich,
                create=create,
                dry_run=dry_run,
                city_of=city_of,
            )
            from_source += len(report.accepted) - before
        # Recorded for every source, spent budget or not: a source that yields exactly its budget
        # and then runs dry logs nothing above, which leaves the run unreadable on the one question
        # it is meant to answer -- where did this run's events actually come from.
        report.proposed_by_source[source.ref] = from_source
    return report
