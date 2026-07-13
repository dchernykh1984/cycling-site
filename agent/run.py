"""Entry point: `python -m agent.run`. Wires real adapters and runs one pipeline. Coverage-omitted."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from agent import fetch, llm, locations, pipeline, sources
from agent.config import ConfigError, from_env
from agent.models import Candidate, RunReport
from agent.site_api import SiteApiClient

_ROOT = Path(__file__).resolve().parent.parent
_SOURCES_FILE = _ROOT / "events_sources.txt"
_GUIDANCE_FILE = _ROOT / "agent" / "guidance.md"


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
    for ref, reason in report.skipped_sources:
        lines.append(f"  ~ source skipped: {ref} ({reason})")
    for title, error in report.post_errors:
        lines.append(f"  ! post failed: {title} ({error})")
    return "\n".join(lines)


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
    cities = locations.flatten_cities(client.location_tree())

    def extract(text: str, source: sources.Source) -> list:
        raw = llm.extract_raw(text, source, guidance, known, taxonomy, config)
        return pipeline.parse_candidates(raw, source.fetch_url or "", taxonomy)

    def resolve_location(candidate: Candidate) -> int | None:
        """Concrete start venue when the city is known and named; else the city's catch-all; else none."""
        city_id = locations.match_city(cities, candidate.city, candidate.region, candidate.country)
        if city_id is None:
            return None  # reviewer adds the location (the guidance tells the LLM to note it)
        if candidate.venue:
            return client.propose_venue(
                city_id, candidate.venue, candidate.venue_kk, candidate.venue_en, candidate.lat, candidate.lng
            )
        return client.fallback_venue(city_id)

    def create(candidate: Candidate) -> None:
        client.create(candidate, resolve_location(candidate))
        # Feed it back so later sources in this same run do not re-propose the same event.
        known.existing.append({"title": candidate.title, "date_start": candidate.date_start})

    report = pipeline.run_pipeline(
        parsed_sources,
        known,
        fetch=fetch.fetch_source,
        extract=extract,
        create=create,
        max_events=config.max_events,
        dry_run=config.dry_run,
    )
    print(_summary(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
