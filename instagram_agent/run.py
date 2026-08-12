"""Entry point: `python -m instagram_agent.run`. Wires the real adapters and runs one pass.

The Instagram agent proposes the small rides a club announces to its followers and nowhere else --
the Saturday coffee ride, a kids' start -- which is the half of the calendar no website carries.

It is its own agent, on its own schedule, reading its own accounts file, but it shares the parts
that must not diverge: the events the site already knows, the duplicate detection those feed, the
location tree, and the API it posts through. Two agents with their own idea of what exists would
propose each other's events back.
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
from instagram_agent import config as insta_config
from instagram_agent import fetch, geo, llm
from instagram_agent.accounts import Account, parse_accounts
from instagram_agent.attribution import credit_account

_ROOT = Path(__file__).resolve().parent.parent
_ACCOUNTS_FILE = _ROOT / "instagram_accounts.yaml"
# How far from a city's own point a meeting place may still be in it. Almaty spans some 25 km, and
# a club ride can start at a reservoir on the edge of one, so this is deliberately generous: it is
# here to catch a geocoder answering with another country, not to police the city limits.
_CITY_RADIUS_METRES = 60_000
# Its own guidance, not the events agent's: that one is told to skip club and social rides, which
# are exactly what this agent exists to find.
_GUIDANCE_FILE = Path(__file__).resolve().parent / "guidance.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _place(candidate: Candidate) -> str:
    parts = [part for part in (candidate.country, candidate.region, candidate.city, candidate.venue) if part]
    where = " / ".join(parts) if parts else "(no place)"
    if candidate.lat is None or candidate.lng is None:
        return f"{where} (no point)"
    return f"{where} ({candidate.lat:.5f}, {candidate.lng:.5f})"


def summary(report: RunReport) -> str:
    """What the run did, in the shape the web agent reports it -- one reader for both logs."""
    verb = "would propose" if report.dry_run else "proposed"
    lines = [
        f"{verb}: {len(report.accepted)}" + (" (capped at limit)" if report.capped else ""),
        f"skipped candidates: {len(report.skipped_candidates)}, "
        f"unreadable accounts: {len(report.skipped_sources)}, post errors: {len(report.post_errors)}",
    ]
    for candidate in report.accepted:
        lines.append(f"  + {candidate.date_start} {candidate.title}")
        lines.append(f"      place: {_place(candidate)}")
    for title, reason in report.skipped_candidates:
        lines.append(f"  - skipped: {title} ({reason})")
    for ref, reason in report.skipped_sources:
        lines.append(f"  ~ account unreadable: {ref} ({reason})")
    for title, error in report.post_errors:
        lines.append(f"  ! post failed: {title} ({error})")
    for ref, count in report.extracted:
        lines.append(f"  = {ref}: {count} extracted, {report.proposed_by_source.get(ref, 0)} proposed")
    return "\n".join(lines)


def as_source(account: Account) -> Source:
    """An account in the shape the shared pipeline handles sources in."""
    return Source(
        kind="instagram",
        ref=f"@{account.username}",
        fetch_url=f"https://www.instagram.com/{account.username}/",
        hint=account.hint,
    )


def read_account(account: Account, recent_days: int, max_posts: int, today: datetime.date) -> str:
    """The account's recent posts as prompt text. Raises AccountUnavailableError when it cannot be read."""
    posts = fetch.fetch_posts(account)
    return fetch.account_text(account, posts[:max_posts], recent_days, today)


def _what_the_site_knows(client: SiteApiClient) -> tuple[KnownEvents, Taxonomy, list]:
    """The events, taxonomy and geography a run is judged against, with the block-list reported."""
    known = client.known()
    print(
        f"known: {len(known.existing)} events, {len(known.rejected)} rejected; "
        f"{known.deleted_count} of these are deleted and blocked from coming back",
        flush=True,
    )
    return known, client.taxonomy(), client.location_tree()


def selected(accounts: list[Account], only: str) -> list[Account]:
    """The accounts this run reads: the one it was pointed at, or all of them when it was not."""
    if not only:
        return accounts
    return [account for account in accounts if account.username.lower() == only.lower()]


def main() -> int:
    try:
        config = insta_config.from_env(dict(os.environ))
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    accounts = selected(parse_accounts(_read(_ACCOUNTS_FILE)), config.only_account)
    if not accounts:
        if config.only_account:
            # A name the file does not carry is a broken workflow, not a quiet night: the matrix is
            # built from this very file, so the two can only disagree if something is wrong.
            print(f"No enabled account named {config.only_account!r} in {_ACCOUNTS_FILE.name}.", file=sys.stderr)
            return 2
        print(f"No enabled accounts in {_ACCOUNTS_FILE.name} -- nothing to do.")
        return 0

    client = SiteApiClient(config.site_base_url, config.api_token)
    known, taxonomy, tree = _what_the_site_knows(client)
    print(_run(config, accounts, client, known, taxonomy, tree))
    return 0


def _run(
    config: insta_config.Config,
    accounts: list[Account],
    client: SiteApiClient,
    known: KnownEvents,
    taxonomy: Taxonomy,
    tree: list,
) -> str:
    """One pass over the accounts, through the same pipeline the web agent runs on."""
    guidance = _read(_GUIDANCE_FILE)
    cities = locations.flatten_cities(tree)
    today = datetime.date.today()
    agent_config = insta_config.as_agent_config(config)
    by_ref = {as_source(account).ref: account for account in accounts}

    def fetch_source(source: Source) -> str:
        return read_account(by_ref[source.ref], config.recent_days, config.max_posts, today)

    def extract(text: str, source: Source) -> list[Candidate]:
        account = by_ref[source.ref]
        raw = llm.extract_raw(text, account, guidance, known, taxonomy, agent_config, today.isoformat())
        parsed = pipeline.parse_candidates(raw, "", taxonomy)
        # A non-empty reply that parses to nothing is a silent drop (a bad field), not the model
        # declining -- surface it so the two are told apart without another run.
        if not parsed and raw.strip() not in ("", "[]"):
            print(f"  . {source.ref}: {len(raw)}-char reply parsed to 0: {' '.join(raw.split())[:400]}", flush=True)
        placed = (_located(_with_account_city(candidate, account), tree, cities) for candidate in parsed)
        return [credit_account(candidate, account) for candidate in placed]

    def city_of(candidate: Candidate) -> int | None:
        return locations.match_city(cities, candidate.city, candidate.region, candidate.country)

    def create(candidate: Candidate) -> None:
        _create(client, tree, cities, known, candidate)

    report = pipeline.run_pipeline(
        [as_source(account) for account in accounts],
        known,
        fetch=fetch_source,
        extract=extract,
        create=create,
        max_events=config.max_events,
        dry_run=config.dry_run,
        city_of=city_of,
    )
    return summary(report)


def _located(candidate: Candidate, tree: list, cities: list) -> Candidate:
    """Give the candidate the point its meeting place sits at, when the post named one.

    A post says where to gather and never says where that is: no coordinates, and each club writes
    the same corner its own way. Without a point the event lands on a node with no place on the map,
    and a fourth node gets added for a car park the site already carries three times.

    Done while the candidates are read rather than when one is posted, so a dry run shows the point
    too -- otherwise the only way to see whether this works is to let a run post something.
    """
    if not candidate.venue or (candidate.lat is not None and candidate.lng is not None):
        return candidate
    point = geo.locate(candidate.venue, candidate.city, candidate.country)
    if point is None:
        return candidate
    city_id = locations.match_city(cities, candidate.city, candidate.region, candidate.country)
    if city_id is not None and not _near_its_city(point, tree, city_id):
        # A geocoder handed an address it does not know answers with something of that name
        # elsewhere -- a river, a village in another country. Anything outside the city the post
        # named is that, not the meeting point.
        print(f"  ~ geocoder placed {candidate.venue!r} outside {candidate.city!r}; ignoring it", flush=True)
        return candidate
    print(f"  * {candidate.venue!r} is at {point[0]:.5f}, {point[1]:.5f}", flush=True)
    placed = replace(candidate, lat=point[0], lng=point[1])
    already = _venue_already_there(tree, cities, placed)
    if already is not None:  # said here rather than when posting, so a dry run shows it too
        print(f"  * {placed.venue!r} is a place the site already has (#{already})", flush=True)
    return placed


def _near_its_city(point: geo.Point, tree: list, city_id: int) -> bool:
    """Whether a geocoded point is close enough to the city to be in it. Unknown city means yes."""
    apart = geo.distance_metres(point, geo.city_point(tree, city_id))
    return apart is None or apart <= _CITY_RADIUS_METRES


def _create(client: SiteApiClient, tree: list, cities: list, known: KnownEvents, candidate: Candidate) -> None:
    """Place the event and post it; name any geography left behind when the post itself fails."""
    created: list[str] = []
    try:
        location_id = _venue_for(client, tree, cities, candidate, created)
        client.create(candidate, location_id)
    except Exception as exc:
        if created:
            raise RuntimeError(f"{exc} (left behind: {', '.join(created)})") from exc
        raise
    # Feed it back, so the next account in this same run does not propose the same ride.
    titles = [t for t in (candidate.title, candidate.title_kk, candidate.title_en) if t]
    known.existing.append({"title": candidate.title, "titles": titles, "date_start": candidate.date_start})


def _venue_for(client: SiteApiClient, tree: list, cities: list, candidate: Candidate, created: list) -> int | None:
    """The venue this event starts from: the one the site already has, or a new one as before."""
    existing = _venue_already_there(tree, cities, candidate)
    if existing is not None:
        print(f"  * hung on the venue the site already has (#{existing})", flush=True)
        return existing
    return resolve_location(client, tree, cities, candidate, created=created)


def _venue_already_there(tree: list, cities: list, candidate: Candidate) -> int | None:
    """The venue on the site this candidate starts from, if it is one the site already carries.

    Asked twice: once while reading, where it only reports, and once when posting, where it decides.
    Reading the tree costs nothing, and reusing a venue is the whole point of geocoding the address
    -- if only the posting run said so, a dry run could not show whether any of this works.
    """
    city_id = locations.match_city(cities, candidate.city, candidate.region, candidate.country)
    if city_id is None or not candidate.venue:
        return None
    point = geo.candidate_point(candidate)
    return geo.existing_venue(geo.venues_of(tree, city_id), candidate.venue, point)


def _with_account_city(candidate: Candidate, account: Account) -> Candidate:
    """Fall back to the city the maintainers gave the account when a post never names one.

    A club posts "we meet at the Giant store" because everyone following it knows which city that
    is; the calendar does not, and an event with no place lands nowhere.
    """
    from dataclasses import replace

    if candidate.city or not account.city:
        return candidate
    return replace(candidate, city=account.city, city_en=account.city)


if __name__ == "__main__":
    raise SystemExit(main())
