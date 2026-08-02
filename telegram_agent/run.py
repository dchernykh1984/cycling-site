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
from dataclasses import replace
from pathlib import Path

from agent import locations, pipeline
from agent.config import ConfigError
from agent.models import Candidate, KnownEvents, RunReport, Source, Taxonomy
from agent.placing import resolve_location
from agent.site_api import SiteApiClient
from telegram_agent import config as tg_config
from telegram_agent import fetch, llm
from telegram_agent.attribution import TME_LINK, credit_source, source_label
from telegram_agent.channels import Channel, parse_channels

_ROOT = Path(__file__).resolve().parent.parent
_CHANNELS_FILE = _ROOT / "telegram_channels.yaml"
# Its own guidance, not the events agent's: that one is told to skip club and social rides, which
# are exactly what a private club channel announces.
_GUIDANCE_FILE = Path(__file__).resolve().parent / "guidance.md"


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
    and skips the source. A pseudo-scheme, deliberately: nothing ever requests this address (the
    reads go over MTProto straight to Telegram's data centres, no web domain involved), and spelling
    it without one keeps it from being mistaken for a link the model or an event could carry.
    """
    return Source(kind="telegram", ref=channel.ref, fetch_url=f"mtproto:{channel.ref}", hint=channel.hint)


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
    try:
        telegram = fetch.open_client(config.telegram_api_id, config.telegram_api_hash, config.telegram_session)
    except fetch.ChannelUnavailableError as exc:
        # A revoked session needs the owner's hand, so the run fails -- but with the message that
        # says what to do, not a traceback burying it.
        print(f"Cannot sign in: {exc}", file=sys.stderr)
        return 1
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
    # Display names, learned as each channel is opened; the file itself carries only ids.
    names: dict[str, str] = {}

    # Each channel's window, split into prompt-sized batches while it is read.
    batches: dict[str, list[list[fetch.Message]]] = {}

    def fetch_source(source: Source) -> str:
        channel = by_ref[source.ref]
        names[source.ref], messages, capped = fetch.read_messages(
            telegram, channel, config.recent_hours, config.max_posts
        )
        print(fetch.reading_note(source.ref, messages, config.recent_hours, capped), flush=True)
        batches[source.ref] = fetch.in_batches(messages)
        # The pipeline only hands this text to extract, which reads the batches instead: a day of a
        # busy chat is several prompts, and one string cannot be several prompts.
        return f"{len(messages)} messages"

    def extract(_text: str, source: Source) -> list[Candidate]:
        channel = by_ref[source.ref]
        label = source_label(source.ref, names.get(source.ref, ""))
        found: list[Candidate] = []
        for number, batch in enumerate(batches.get(source.ref, []), start=1):
            text = fetch.channel_text(channel, batch, config.recent_hours, today)
            raw = llm.extract_raw(text, channel, guidance, known, taxonomy, agent_config, today.isoformat())
            parsed = pipeline.parse_candidates(raw, "", taxonomy)
            # A non-empty reply that parses to nothing is a silent drop (a bad field), not the model
            # declining -- surface it so the two are told apart without another run.
            if not parsed and raw.strip() not in ("", "[]"):
                print(
                    f"  . {source.ref} batch {number}: {len(raw)}-char reply parsed to 0: "
                    f"{' '.join(raw.split())[:400]}",
                    flush=True,
                )
            found.extend(credit_source(_scrubbed(_with_channel_city(c, channel)), label) for c in parsed)
        return found

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
        max_per_source=config.max_per_channel,
        dry_run=config.dry_run,
        city_of=city_of,
    )
    return summary(report)


def _scrubbed(candidate: Candidate) -> Candidate:
    """Strip anything that would point back at the channel the announcement was read in.

    The model is told not to write these, and this makes it so regardless -- in the URL fields AND
    in the text: a t.me link pasted into a description would disclose the private source just as
    surely as one in source_url.
    """
    registration = candidate.url_registration if "t.me/" not in candidate.url_registration else ""
    unlink = lambda text: TME_LINK.sub("", text)  # noqa: E731 -- six fields, one rule
    return replace(
        candidate,
        source_url="",
        url_route="",
        url_registration=registration,
        title=unlink(candidate.title),
        title_kk=unlink(candidate.title_kk),
        title_en=unlink(candidate.title_en),
        description=unlink(candidate.description),
        description_kk=unlink(candidate.description_kk),
        description_en=unlink(candidate.description_en),
    )


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
    if candidate.city or not channel.city:
        return candidate
    return replace(candidate, city=channel.city, city_en=channel.city)


if __name__ == "__main__":
    sys.exit(main())
