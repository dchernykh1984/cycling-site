"""Entry point: `python -m agent.run`. Wires real adapters and runs one pipeline. Coverage-omitted."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from agent import chunk, enrich, fetch, geo, llm, locations, pipeline, sources
from agent.config import Config, ConfigError, from_env
from agent.models import Candidate, KnownEvents, RunReport, Taxonomy
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
    for ref, count in report.extracted:
        lines.append(f"  = extracted {count} from {ref}")
    return "\n".join(lines)


def _extract_candidates(
    text: str, source: sources.Source, guidance: str, known: KnownEvents, taxonomy: Taxonomy, config: Config
) -> list:
    """Extract candidates from a source; aggregators are read in line-aligned chunks (agent.chunk)."""
    pieces = chunk.split_source_text(text, _AGGREGATOR_CHUNK_CHARS) if source.kind == "aggregator" else [text]
    candidates: list = []
    for piece in pieces:
        raw = llm.extract_raw(piece, source, guidance, known, taxonomy, config)
        # A calendar's own listing URL announces no single race, so it must not stand in when the
        # model found no link: a reader following it lands on a list of dozens and cannot tell
        # which entry was meant. Leave it empty instead and let the enrichment pass fill it in.
        fallback_url = "" if source.kind == "aggregator" else (source.fetch_url or "")
        parsed = pipeline.parse_candidates(raw, fallback_url, taxonomy)
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


def _propose_city(client, tree: list, cities: list, candidate: Candidate, created: list | None = None) -> int | None:
    """Propose the candidate's city, and its region when that is new too; None if not possible.

    Both land pending: the agent may use them straight away, everyone else sees them once a reviewer
    approves. Countries are admin-only, so an event in a country the site does not carry goes under
    the tree's catch-all country instead of inventing a root.
    """
    # A name that is only punctuation ("-", "()") survives the "not empty" test but normalizes to
    # nothing, so every guard below would pass it through and post it verbatim as a place. Treat a
    # region or city with no real content as absent.
    if not locations.has_real_name(candidate.city) or not locations.has_real_name(candidate.region):
        return None
    if locations.is_ambiguous_city(cities, candidate.city, candidate.region, candidate.country):
        return None
    # The model is told to give a real place and a first-level region, but nothing stops it echoing
    # the site's own placeholder or handing back a district; either one would become a permanent
    # node here, so refuse and let a reviewer place the event instead.
    if locations.is_placeholder_name(
        candidate.city, candidate.city_kk, candidate.city_en, candidate.region, candidate.region_kk, candidate.region_en
    ):
        return None
    country = locations.match_country(tree, candidate.country)
    if country is None or locations.is_catch_all_country(country):
        # Without a country we cannot place anything. And when the name resolved to the tree's
        # "Other country" bucket, the site simply does not carry that country -- hanging a real
        # region under that bucket is structurally meaningless, so leave the event unplaced for a
        # human to add the country and place it. (A content-free region was already refused above.)
        return None
    region = locations.match_region(country, candidate.region)
    if region is None:
        if locations.looks_like_district(candidate.region):
            return None
        region_id = client.propose_place(country["id"], candidate.region, candidate.region_kk, candidate.region_en)
        region = {
            "id": region_id,
            "name": {"ru": candidate.region, "kk": candidate.region_kk, "en": candidate.region_en},
        }
        if created is not None:
            created.append(f"region {candidate.region!r} (#{region_id})")
        country.setdefault("children", []).append(region)
    city_id = client.propose_place(region["id"], candidate.city, candidate.city_kk, candidate.city_en)
    if created is not None:
        created.append(f"city {candidate.city!r} (#{city_id})")
    # Keep the flat index in step so a later candidate in the same run reuses the new city.
    cities.append(
        locations.city_record(city_id, (candidate.city, candidate.city_kk, candidate.city_en), region, country)
    )
    return city_id


def _resolve_location(
    client, tree: list, cities: list, candidate: Candidate, created: list | None = None
) -> int | None:
    """Concrete start venue when the city is known and named; else the city's catch-all.

    A city the tree does not have yet is proposed rather than skipped, so the event is placed from
    the start and the reviewer only has to confirm the geography.
    """
    city_id = locations.match_city(cities, candidate.city, candidate.region, candidate.country)
    if city_id is None:
        city_id = _propose_city(client, tree, cities, candidate, created)
    if city_id is None:
        # Nothing to hang the event on: an unnamed or ambiguous city, or no country/region to
        # place it under. The event is still worth proposing -- the guidance asks the model to
        # repeat the place in the description, so a reviewer can set the location by hand.
        return None
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

    def create(candidate: Candidate) -> None:
        # The geography is posted before the competition, so a failing competition POST leaves it
        # behind. Name what was created in the error the pipeline records, otherwise those pending
        # nodes sit in the moderation queue with nothing explaining where they came from.
        created: list[str] = []
        try:
            location_id = _resolve_location(client, tree, cities, candidate, created=created)
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
