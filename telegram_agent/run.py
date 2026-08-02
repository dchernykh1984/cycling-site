"""Entry point: `python -m telegram_agent.run`. Wires the real adapters and runs one pass.

The Telegram agent reads the channels no other agent can: private club channels and closed
communities that need a member account. It is its own agent, on its own schedule, reading its own
channels file, but it shares the parts that must not diverge: the events the site already knows,
the duplicate detection those feed, the location tree, and the API it posts through.

Unlike the Instagram agent it is a single job over every channel, deliberately: all reads go
through one logged-in session, and a session hopping addresses inside one night is what gets a
session revoked. One process, one connection, channels in sequence.
"""

from __future__ import annotations

import datetime
import os
import sys
from pathlib import Path

from agent import locations, pipeline
from agent.config import ConfigError
from agent.models import Candidate, KnownEvents, RunReport, Source, Taxonomy
from agent.placing import resolve_location
from agent.site_api import SiteApiClient
from telegram_agent import config as tg_config
from telegram_agent import fetch, llm
from telegram_agent.channels import Channel, link_of, parse_channels

_ROOT = Path(__file__).resolve().parent.parent
_CHANNELS_FILE = _ROOT / "telegram_channels.yaml"
# Its own guidance, not the events agent's: that one is told to skip club and social rides, which
# are exactly what a private club channel announces.
_GUIDANCE_FILE = Path(__file__).resolve().parent / "guidance.md"
# What one talkative channel may contribute to a run -- the same per-source budget the events agent
# holds its sources to, so a lively group chat cannot spend the whole night's allowance.
_MAX_PER_CHANNEL = 5


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _place(candidate: Candidate) -> str:
    parts = [part for part in (candidate.country, candidate.region, candidate.city, candidate.venue) if part]
    return " / ".join(parts) if parts else "(no place)"


def summary(report: RunReport) -> str:
    """What the run did, in the shape the other agents report it -- one reader for every log."""
    verb = "would propose" if report.dry_run else "proposed"
    lines = [
        f"{verb}: {len(report.accepted)}" + (" (capped at limit)" if report.capped else ""),
        f"skipped candidates: {len(report.skipped_candidates)}, "
        f"unreadable channels: {len(report.skipped_sources)}, post errors: {len(report.post_errors)}",
    ]
    for candidate in report.accepted:
        lines.append(f"  + {candidate.date_start} {candidate.title}")
        lines.append(f"      place: {_place(candidate)}")
    for title, reason in report.skipped_candidates:
        lines.append(f"  - skipped: {title} ({reason})")
    for ref, reason in report.skipped_sources:
        lines.append(f"  ~ channel unreadable: {ref} ({reason})")
    for title, error in report.post_errors:
        lines.append(f"  ! post failed: {title} ({error})")
    for ref, count in report.extracted:
        lines.append(f"  = {ref}: {count} extracted, {report.proposed_by_source.get(ref, 0)} proposed")
    return "\n".join(lines)


def as_source(channel: Channel) -> Source:
    """A channel in the shape the shared pipeline handles sources in.

    ``fetch_url`` must be set -- the shared pipeline reads a missing one as "cannot be read yet"
    and skips the source. It is never handed to the model or written into an event: extraction
    passes "" for the default source link, and :func:`_scrubbed` holds the door behind that.
    """
    return Source(kind="telegram", ref=channel.ref, fetch_url=link_of(channel.ref), hint=channel.hint)


def _what_the_site_knows(client: SiteApiClient) -> tuple[KnownEvents, Taxonomy, list]:
    """The events, taxonomy and geography a run is judged against, with the block-list reported."""
    known = client.known()
    print(
        f"known: {len(known.existing)} events, {len(known.rejected)} rejected; "
        f"{known.deleted_count} of these are deleted and blocked from coming back",
        flush=True,
    )
    return known, client.taxonomy(), client.location_tree()


def main() -> int:
    try:
        config = tg_config.from_env(dict(os.environ))
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    missing = tg_config.telegram_credentials_missing(dict(os.environ))
    if missing:
        # Not an error: before the service account exists these secrets are absent by design, and
        # the sources the account would read simply stay unread -- exactly the old behaviour.
        print(f"Telegram credentials not set ({', '.join(missing)}) -- nothing this agent can read.")
        return 0

    channels = parse_channels(_read(_CHANNELS_FILE))
    if not channels:
        print(f"No enabled channels in {_CHANNELS_FILE.name} -- nothing to do.")
        return 0

    client = SiteApiClient(config.site_base_url, config.api_token)
    known, taxonomy, tree = _what_the_site_knows(client)
    telegram = fetch.open_client(config.telegram_api_id, config.telegram_api_hash, config.telegram_session)
    try:
        print(_run(config, channels, client, telegram, known, taxonomy, tree))
    finally:
        telegram.disconnect()
    return 0


def _run(
    config: tg_config.Config,
    channels: list[Channel],
    client: SiteApiClient,
    telegram: object,
    known: KnownEvents,
    taxonomy: Taxonomy,
    tree: list,
) -> str:
    """One pass over the channels, through the same pipeline the other agents run on."""
    guidance = _read(_GUIDANCE_FILE)
    cities = locations.flatten_cities(tree)
    today = datetime.date.today()
    agent_config = tg_config.as_agent_config(config)
    by_ref = {channel.ref: channel for channel in channels}

    def fetch_source(source: Source) -> str:
        channel = by_ref[source.ref]
        messages = fetch.read_messages(telegram, channel, config.max_posts)
        return fetch.channel_text(channel, messages, config.recent_days, today)

    def extract(text: str, source: Source) -> list[Candidate]:
        channel = by_ref[source.ref]
        raw = llm.extract_raw(text, channel, guidance, known, taxonomy, agent_config, today.isoformat())
        parsed = pipeline.parse_candidates(raw, "", taxonomy)
        # A non-empty reply that parses to nothing is a silent drop (a bad field), not the model
        # declining -- surface it so the two are told apart without another run.
        if not parsed and raw.strip() not in ("", "[]"):
            print(f"  . {source.ref}: {len(raw)}-char reply parsed to 0: {' '.join(raw.split())[:400]}", flush=True)
        return [_scrubbed(_with_channel_city(candidate, channel)) for candidate in parsed]

    def city_of(candidate: Candidate) -> int | None:
        return locations.match_city(cities, candidate.city, candidate.region, candidate.country)

    def create(candidate: Candidate) -> None:
        _create(client, tree, cities, known, candidate)

    report = pipeline.run_pipeline(
        [as_source(channel) for channel in channels],
        known,
        fetch=fetch_source,
        extract=extract,
        create=create,
        max_events=config.max_events,
        max_per_source=_MAX_PER_CHANNEL,
        dry_run=config.dry_run,
        city_of=city_of,
    )
    return summary(report)


def _scrubbed(candidate: Candidate) -> Candidate:
    """Strip anything that would point back at the channel the announcement was read in.

    The model is told not to write these, and this makes it so regardless: no source link ever, and
    a registration link only when it leads outside Telegram -- a t.me link is either the private
    channel itself or something a reader without the invite cannot open anyway.
    """
    from dataclasses import replace

    registration = candidate.url_registration if "t.me/" not in candidate.url_registration else ""
    return replace(candidate, source_url="", url_route="", url_registration=registration)


def _create(client: SiteApiClient, tree: list, cities: list, known: KnownEvents, candidate: Candidate) -> None:
    """Place the event and post it; name any geography left behind when the post itself fails."""
    created: list[str] = []
    try:
        location_id = resolve_location(client, tree, cities, candidate, created=created)
        client.create(candidate, location_id)
    except Exception as exc:
        if created:
            raise RuntimeError(f"{exc} (left behind: {', '.join(created)})") from exc
        raise
    # Feed it back, so the next channel in this same run does not propose the same ride.
    titles = [t for t in (candidate.title, candidate.title_kk, candidate.title_en) if t]
    known.existing.append({"title": candidate.title, "titles": titles, "date_start": candidate.date_start})


def _with_channel_city(candidate: Candidate, channel: Channel) -> Candidate:
    """Fall back to the city the maintainers gave the channel when a message never names one.

    Inside a club's own chat nobody says which city they are in -- everyone knows. The maintainers
    do too, and wrote it next to the channel.
    """
    from dataclasses import replace

    if candidate.city or not channel.city:
        return candidate
    return replace(candidate, city=channel.city, city_en=channel.city)


if __name__ == "__main__":
    sys.exit(main())
