"""Entry point: `python -m agent.run`. Wires real adapters and runs one pipeline. Coverage-omitted."""

from __future__ import annotations

import os
import sys
from dataclasses import replace
from pathlib import Path

from agent import chunk, enrich, fetch, geo, links, llm, locations, pipeline, sources
from agent.config import Config, ConfigError, from_env
from agent.models import Candidate, KnownEvents, RunReport, Taxonomy
from agent.placing import resolve_location
from agent.site_api import SiteApiClient

_ROOT = Path(__file__).resolve().parent.parent
_SOURCES_FILE = _ROOT / "events_sources.yaml"
_GUIDANCE_FILE = _ROOT / "agent" / "guidance.md"
# Aggregator calendars are extracted in line-aligned chunks so the model enumerates every terse row
# instead of dropping some from one long prompt; other sources stay a single pass. The chunk is kept
# small because each event expands to a verbose JSON object (title, description, venue etc. in three
# locales): a dense calendar of ~30 rows overflows the model's output-token limit and the reply comes
# back truncated, so a smaller input chunk keeps the whole reply within budget.
_AGGREGATOR_CHUNK_CHARS = 3000


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _place(candidate: Candidate) -> str:
    """The geography and start coordinate a candidate carries, for the run summary.

    Without this a dry run reports only a title and a date, which cannot answer the two questions
    a run is actually judged on -- did the event get a real venue, and did a start coordinate come
    out of its track. Printed even when empty, so a missing place is visible rather than absent.
    """
    parts = [part for part in (candidate.country, candidate.region, candidate.city, candidate.venue) if part]
    place = " / ".join(parts) if parts else "(no place)"
    if candidate.lat is not None and candidate.lng is not None:
        return f"{place} ({candidate.lat}, {candidate.lng})"
    return f"{place} (no coordinate)"


def _summary(report: RunReport) -> str:
    verb = "would propose" if report.dry_run else "proposed"
    lines = [
        f"{verb}: {len(report.accepted)}" + (" (capped at limit)" if report.capped else ""),
        f"skipped candidates: {len(report.skipped_candidates)}, "
        f"skipped sources: {len(report.skipped_sources)}, post errors: {len(report.post_errors)}",
    ]
    for candidate in report.accepted:
        lines.append(f"  + {candidate.date_start} {candidate.title}")
        lines.append(f"      link:  {candidate.source_url or '(none)'}")
        lines.append(f"      place: {_place(candidate)}")
    for title, reason in report.skipped_candidates:
        lines.append(f"  - skipped: {title} ({reason})")
    for ref, reason in report.skipped_sources:
        lines.append(f"  ~ source skipped: {ref} ({reason})")
    for title, error in report.post_errors:
        lines.append(f"  ! post failed: {title} ({error})")
    for ref, count in report.extracted:
        lines.append(f"  = {ref}: {count} extracted, {report.proposed_by_source.get(ref, 0)} proposed")
    for ref in report.source_capped:
        lines.append(f"  # {ref} reached its per-source limit")
    return "\n".join(lines)


def _reader(page_links: dict[str, list[tuple[str, str]]]):
    """Read a source, remembering every link its page carried for the matching step later."""

    def read(source: sources.Source) -> str:
        text, found = fetch.source_text_and_links(source)
        page_links[source.ref] = found
        return text

    return read


def _with_own_link(candidate: Candidate, page_text: str, page_links: list[tuple[str, str]]) -> Candidate:
    """Fill an empty announcement link from the page's own list of links, by the event's name.

    Matched against every link the page carries, not the excerpt the prompt was given: the excerpt
    is capped to keep the prompt readable, and the race is as likely to be below the cap as above
    it. Falls back to the links quoted in the text when the caller has no list of its own.
    """
    if candidate.source_url:
        return candidate
    found = links.link_for_title(candidate.title, page_links or links.labelled_links(page_text))
    return replace(candidate, source_url=found) if found else candidate


def _extract_candidates(
    text: str,
    source: sources.Source,
    guidance: str,
    known: KnownEvents,
    taxonomy: Taxonomy,
    config: Config,
    page_links: list[tuple[str, str]] | None = None,
) -> list:
    """Extract candidates from a source; aggregators are read in line-aligned chunks (agent.chunk)."""
    pieces = chunk.split_source_text(text, _AGGREGATOR_CHUNK_CHARS) if source.kind == "aggregator" else [text]
    candidates: list = []
    for piece in pieces:
        raw = llm.extract_raw(piece, source, guidance, known, taxonomy, config)
        # A listing announces no single race, so it must not stand in when the model found no link:
        # a reader following it lands among dozens of announcements and cannot tell which entry was
        # meant. A calendar is a listing by what it is, whatever its address looks like; a forum
        # index and a Telegram channel feed are listings by their address, whichever section of the
        # sources file they were written in. Both are left empty for the enrichment pass to fill.
        source_url = source.fetch_url or ""
        is_listing = source.kind == "aggregator" or not links.announces_one_event(source_url)
        fallback_url = "" if is_listing else source_url
        parsed = pipeline.parse_candidates(raw, fallback_url, taxonomy)
        # The model sometimes returns nothing for source_url even though the page lists the race
        # under its own name. The list is right there in the text it was given, so read it back
        # rather than publish an event with no way to reach its announcement.
        parsed = [_with_own_link(candidate, piece, page_links or []) for candidate in parsed]
        # A non-empty reply that parses to nothing is a silent drop (a bad field), not the model
        # declining -- surface the raw reply so the two are told apart without another run.
        if not parsed and raw.strip() not in ("", "[]"):
            print(f"  . {source.ref}: {len(raw)}-char reply parsed to 0: {' '.join(raw.split())[:400]}", flush=True)
        candidates.extend(parsed)
    return candidates


def _add_start_coordinate(candidate: Candidate, page_text: str) -> Candidate:
    """Give a venue its real start point from the track the page links to, if it has no coordinate.

    Announcement pages seldom print lat/lng, but they link the route (a .gpx/.kml, a route.eduha
    track, a RideWithGPS route); its first point is the start line. Only fills a coordinate the model
    did not already provide, and only when a venue is being proposed.
    """
    from dataclasses import replace

    if not candidate.venue or candidate.lat is not None or candidate.lng is not None:
        return candidate
    # Prefer the route link the model already picked out (url_route) -- it is the event's own track;
    # fall back to scanning the page's links only if it named none.
    page_links = page_text.partition("Links on the page:")[2].split()
    links = ([candidate.url_route] if candidate.url_route else []) + page_links
    coord = geo.start_coordinate(links, fetch.fetch_track)
    if coord is None:
        return candidate
    print(f"  * start coordinate {coord} for {candidate.title!r} (venue {candidate.venue!r})", flush=True)
    return replace(candidate, lat=coord[0], lng=coord[1])


def main() -> int:
    try:
        config = from_env(dict(os.environ))
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    client = SiteApiClient(config.site_base_url, config.api_token)
    guidance = _read(_GUIDANCE_FILE)
    parsed_sources = sources.parse_sources(_read(_SOURCES_FILE))
    known = client.known()
    print(
        f"known: {len(known.existing)} events, {len(known.rejected)} rejected; "
        f"{known.deleted_count} of these are deleted and blocked from coming back",
        flush=True,
    )
    taxonomy = client.taxonomy()
    tree = client.location_tree()
    cities = locations.flatten_cities(tree)

    # Every link each source's page carried, learned while it was read; the prompt only ever sees
    # a capped excerpt of these (agent.fetch.source_text_and_links).
    page_links: dict[str, list[tuple[str, str]]] = {}

    def extract(text: str, source: sources.Source) -> list:
        return _extract_candidates(text, source, guidance, known, taxonomy, config, page_links.get(source.ref))

    def enrich_candidate(candidate: Candidate) -> Candidate:
        """Fetch the event's own page and let the LLM refine it; keep the original on any failure."""
        if not config.enrich_details or not enrich.should_enrich(candidate):
            return candidate
        try:
            page_text = fetch.fetch_url(candidate.source_url)
            raw = llm.enrich_raw(candidate, page_text, guidance, taxonomy, config)
            refined = pipeline.parse_candidates(raw, candidate.source_url, taxonomy)
        except Exception:
            return candidate  # network/LLM/parse failure -> use what we already have
        merged = enrich.merge_candidate(candidate, refined[0]) if refined else candidate
        return _add_start_coordinate(merged, page_text)

    def city_of(candidate: Candidate) -> int | None:
        """The site city a candidate starts in, for duplicate detection. Never creates anything:
        an unknown city simply means the place cannot rule a duplicate in or out."""
        return locations.match_city(cities, candidate.city, candidate.region, candidate.country)

    def create(candidate: Candidate) -> None:
        # The geography is posted before the competition, so a failing competition POST leaves it
        # behind. Name what was created in the error the pipeline records, otherwise those pending
        # nodes sit in the moderation queue with nothing explaining where they came from.
        created: list[str] = []
        try:
            location_id = resolve_location(client, tree, cities, candidate, created=created)
            client.create(candidate, location_id)
        except Exception as exc:
            if created:
                raise RuntimeError(f"{exc} (left behind: {', '.join(created)})") from exc
            raise
        # Feed it back so later sources in this same run do not re-propose the same event.
        titles = [t for t in (candidate.title, candidate.title_kk, candidate.title_en) if t]
        known.existing.append({"title": candidate.title, "titles": titles, "date_start": candidate.date_start})

    report = pipeline.run_pipeline(
        parsed_sources,
        known,
        fetch=_reader(page_links),
        extract=extract,
        create=create,
        max_events=config.max_events,
        max_per_source=config.max_per_source,
        city_of=city_of,
        dry_run=config.dry_run,
        enrich=enrich_candidate,
    )
    print(_summary(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
