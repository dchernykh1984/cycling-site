"""Entry point: `python -m agent.run`. Wires real adapters and runs one pipeline. Coverage-omitted."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from agent import chunk, enrich, fetch, llm, locations, pipeline, sources
from agent.config import Config, ConfigError, from_env
from agent.models import Candidate, KnownEvents, RunReport, Taxonomy
from agent.site_api import SiteApiClient

_ROOT = Path(__file__).resolve().parent.parent
_SOURCES_FILE = _ROOT / "events_sources.yaml"
_GUIDANCE_FILE = _ROOT / "agent" / "guidance.md"
# Aggregator calendars are extracted in line-aligned chunks so the model enumerates every terse row
# instead of dropping some from one long prompt; other sources stay a single pass.
_AGGREGATOR_CHUNK_CHARS = 6000


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _summary(report: RunReport) -> str:
    verb = "would propose" if report.dry_run else "proposed"
    lines = [
        f"{verb}: {len(report.accepted)}" + (" (capped at limit)" if report.capped else ""),
        f"skipped candidates: {len(report.skipped_candidates)}, "
        f"skipped sources: {len(report.skipped_sources)}, post errors: {len(report.post_errors)}",
    ]
    for candidate in report.accepted:
        lines.append(f"  + {candidate.date_start} {candidate.title}")
    for title, reason in report.skipped_candidates:
        lines.append(f"  - skipped: {title} ({reason})")
    for ref, reason in report.skipped_sources:
        lines.append(f"  ~ source skipped: {ref} ({reason})")
    for title, error in report.post_errors:
        lines.append(f"  ! post failed: {title} ({error})")
    return "\n".join(lines)


def _extract_candidates(
    text: str, source: sources.Source, guidance: str, known: KnownEvents, taxonomy: Taxonomy, config: Config
) -> list:
    """Extract candidates from a source; aggregators are read in line-aligned chunks (agent.chunk)."""
    pieces = chunk.split_source_text(text, _AGGREGATOR_CHUNK_CHARS) if source.kind == "aggregator" else [text]
    candidates: list = []
    for piece in pieces:
        raw = llm.extract_raw(piece, source, guidance, known, taxonomy, config)
        candidates.extend(pipeline.parse_candidates(raw, source.fetch_url or "", taxonomy))
    return candidates


def _propose_city(client, tree: list, cities: list, candidate: Candidate) -> int | None:
    """Propose the candidate's city, and its region when that is new too; None if not possible.

    Both land pending: the agent may use them straight away, everyone else sees them once a reviewer
    approves. Countries are admin-only, so an event in a country the site does not carry goes under
    the tree's catch-all country instead of inventing a root.
    """
    if not candidate.city or locations.is_ambiguous_city(cities, candidate.city, candidate.region, candidate.country):
        return None
    country = locations.match_country(tree, candidate.country)
    if country is None or not candidate.region:
        # Without a country we cannot place anything, and without a region there is nothing to hang
        # the city on: the tree's catch-all regions are hidden, so the API never hands them to us.
        return None
    region = locations.match_region(country, candidate.region)
    if region is None:
        region = {"id": client.propose_place(country["id"], candidate.region), "name": candidate.region}
        country.setdefault("children", []).append(region)
    city_id = client.propose_place(region["id"], candidate.city)
    # Keep the flat index in step so a later candidate in the same run reuses the new city.
    cities.append(locations.city_record(city_id, candidate.city, region, country))
    return city_id


def _resolve_location(client, tree: list, cities: list, candidate: Candidate) -> int | None:
    """Concrete start venue when the city is known and named; else the city's catch-all.

    A city the tree does not have yet is proposed rather than skipped, so the event is placed from
    the start and the reviewer only has to confirm the geography.
    """
    city_id = locations.match_city(cities, candidate.city, candidate.region, candidate.country)
    if city_id is None:
        city_id = _propose_city(client, tree, cities, candidate)
    if city_id is None:
        return None  # reviewer adds the location (the guidance tells the LLM to note it)
    if candidate.venue:
        return client.propose_venue(
            city_id, candidate.venue, candidate.venue_kk, candidate.venue_en, candidate.lat, candidate.lng
        )
    return client.fallback_venue(city_id)


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
    taxonomy = client.taxonomy()
    tree = client.location_tree()
    cities = locations.flatten_cities(tree)

    def extract(text: str, source: sources.Source) -> list:
        return _extract_candidates(text, source, guidance, known, taxonomy, config)

    def resolve_location(candidate: Candidate) -> int | None:
        return _resolve_location(client, tree, cities, candidate)

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
        return enrich.merge_candidate(candidate, refined[0]) if refined else candidate

    def create(candidate: Candidate) -> None:
        client.create(candidate, resolve_location(candidate))
        # Feed it back so later sources in this same run do not re-propose the same event.
        titles = [t for t in (candidate.title, candidate.title_kk, candidate.title_en) if t]
        known.existing.append({"title": candidate.title, "titles": titles, "date_start": candidate.date_start})

    report = pipeline.run_pipeline(
        parsed_sources,
        known,
        fetch=fetch.fetch_source,
        extract=extract,
        create=create,
        max_events=config.max_events,
        dry_run=config.dry_run,
        enrich=enrich_candidate,
    )
    print(_summary(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
