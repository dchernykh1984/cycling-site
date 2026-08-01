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
from pathlib import Path

from agent import locations, pipeline
from agent.config import ConfigError
from agent.models import Candidate, KnownEvents, RunReport, Source, Taxonomy
from agent.placing import resolve_location
from agent.site_api import SiteApiClient
from instagram_agent import config as insta_config
from instagram_agent import fetch, llm
from instagram_agent.accounts import Account, parse_accounts

_ROOT = Path(__file__).resolve().parent.parent
_ACCOUNTS_FILE = _ROOT / "instagram_accounts.yaml"
_GUIDANCE_FILE = _ROOT / "agent" / "guidance.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _place(candidate: Candidate) -> str:
    parts = [part for part in (candidate.country, candidate.region, candidate.city, candidate.venue) if part]
    return " / ".join(parts) if parts else "(no place)"


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
        lines.append(f"      link:  {candidate.source_url or '(none)'}")
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


def main() -> int:
    try:
        config = insta_config.from_env(dict(os.environ))
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    accounts = parse_accounts(_read(_ACCOUNTS_FILE))
    if not accounts:
        print("No enabled accounts in instagram_accounts.yaml -- nothing to do.")
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
    read_so_far = 0

    def fetch_source(source: Source) -> str:
        # Accounts are read one at a time with a pause between them: a burst of requests is what
        # Instagram answers with an error, and a nightly run is in no hurry.
        nonlocal read_so_far
        if read_so_far:
            fetch.pause_between_accounts()
        read_so_far += 1
        return read_account(by_ref[source.ref], config.recent_days, config.max_posts, today)

    def extract(text: str, source: Source) -> list[Candidate]:
        account = by_ref[source.ref]
        raw = llm.extract_raw(text, account, guidance, known, taxonomy, agent_config, today.isoformat())
        parsed = pipeline.parse_candidates(raw, "", taxonomy)
        # A non-empty reply that parses to nothing is a silent drop (a bad field), not the model
        # declining -- surface it so the two are told apart without another run.
        if not parsed and raw.strip() not in ("", "[]"):
            print(f"  . {source.ref}: {len(raw)}-char reply parsed to 0: {' '.join(raw.split())[:400]}", flush=True)
        return [_with_account_city(candidate, account) for candidate in parsed]

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
    # Feed it back, so the next account in this same run does not propose the same ride.
    titles = [t for t in (candidate.title, candidate.title_kk, candidate.title_en) if t]
    known.existing.append({"title": candidate.title, "titles": titles, "date_start": candidate.date_start})


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
