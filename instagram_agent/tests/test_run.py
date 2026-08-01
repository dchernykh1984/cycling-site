"""The run itself: reading accounts, holding the limit, and reporting what it did."""

import datetime

from agent.models import Candidate, KnownEvents, RunReport
from agent.pipeline import run_pipeline
from instagram_agent.accounts import Account
from instagram_agent.run import _with_account_city, as_source, read_account, summary

TODAY = datetime.date(2026, 8, 1)


def _candidate(title="Early Bird Ride", date="2026-08-08", **kwargs):
    return Candidate(title=title, date_start=date, description="d", **kwargs)


def _run(sources, by_source, *, max_events=10, dry_run=False):
    created = []
    report = run_pipeline(
        sources,
        KnownEvents(),
        fetch=lambda s: "text",
        extract=lambda text, s: by_source.get(s.ref, []),
        create=created.append,
        max_events=max_events,
        dry_run=dry_run,
        today=TODAY,
    )
    return report, created


def test_an_account_becomes_a_source_the_shared_pipeline_understands():
    source = as_source(Account("ubtalmaty", hint="a club"))
    assert source.kind == "instagram"
    assert source.ref == "@ubtalmaty"
    assert source.fetch_url == "https://www.instagram.com/ubtalmaty/"
    assert source.hint == "a club"


def test_the_limit_caps_how_many_events_one_run_proposes():
    source = as_source(Account("ubtalmaty"))
    many = [_candidate(title=f"Ride {n}", date=f"2026-08-{n + 10:02d}") for n in range(8)]
    report, created = _run([source], {source.ref: many}, max_events=3)
    assert len(report.accepted) == 3
    assert report.capped is True
    assert len(created) == 3


def test_a_dry_run_proposes_without_posting_anything():
    source = as_source(Account("ubtalmaty"))
    report, created = _run([source], {source.ref: [_candidate()]}, dry_run=True)
    assert [c.title for c in report.accepted] == ["Early Bird Ride"]
    assert created == []


def test_a_ride_with_no_city_takes_the_one_the_account_was_given():
    account = Account("ubtalmaty", city="Almaty")
    placed = _with_account_city(_candidate(), account)
    assert (placed.city, placed.city_en) == ("Almaty", "Almaty")


def test_a_city_the_post_named_is_not_overwritten():
    account = Account("ubtalmaty", city="Almaty")
    placed = _with_account_city(_candidate(city="Talgar"), account)
    assert placed.city == "Talgar"


def test_an_account_without_a_city_leaves_the_candidate_alone():
    assert _with_account_city(_candidate(), Account("ubtalmaty")).city == ""


def test_reading_an_account_keeps_only_the_newest_posts():
    """The post limit is what keeps a chatty account from filling the prompt with a fortnight."""
    import instagram_agent.fetch as fetch_module
    from instagram_agent.fetch import Post

    posts = [Post(f"Sc{n}", f"post number {n}", datetime.date(2026, 7, 31)) for n in range(6)]
    original = fetch_module.fetch_posts
    try:
        fetch_module.fetch_posts = lambda account: posts
        text = read_account(Account("ubtalmaty"), recent_days=21, max_posts=2, today=TODAY)
    finally:
        fetch_module.fetch_posts = original
    assert "post number 0" in text and "post number 1" in text
    assert "post number 2" not in text


def test_the_summary_names_each_proposal_and_its_place_but_never_a_post():
    """Even the run log stays clear of the platform: this repository is public."""
    report = RunReport(dry_run=True)
    report.accepted.append(_candidate(country="KZ", city="Almaty", venue="Giant Abay 47"))
    report.extracted.append(("@ubtalmaty", 4))
    report.proposed_by_source["@ubtalmaty"] = 1
    out = summary(report)
    assert "would propose: 1" in out
    assert "place: KZ / Almaty / Giant Abay 47" in out
    assert "@ubtalmaty: 4 extracted, 1 proposed" in out
    assert "instagram.com" not in out.lower()


def test_the_summary_separates_an_unreadable_account_from_a_quiet_one():
    report = RunReport()
    report.skipped_sources.append(("@someone", "not a professional account"))
    out = summary(report)
    assert "unreadable accounts: 1" in out
    assert "account unreadable: @someone (not a professional account)" in out


def test_a_reply_in_the_agreed_schema_becomes_a_placed_three_locale_event():
    """The contract between this agent's prompt and the shared parser, in one test.

    If the schema in the prompt drifts from what agent.pipeline reads, events lose their locales or
    their link and nobody notices until a run posts something half-empty.
    """
    from agent.pipeline import parse_candidates

    reply = """[{
      "title": {"ru": "Early Bird Coffee Ride", "kk": "Erte Coffee Ride", "en": "Early Bird Coffee Ride"},
      "date_start": "2026-08-08",
      "description": {"ru": "<p>Sbor 5:45</p>", "kk": "<p>Zhinalu 5:45</p>", "en": "<p>Gather 5:45</p>"},
      "source_url": "https://www.instagram.com/p/Abc123/",
      "city": {"ru": "Almaty", "kk": "Almaty", "en": "Almaty"},
      "venue": {"ru": "Giant Abay 47", "kk": "Giant Abay 47", "en": "Giant Abay 47"},
      "country": "KZ", "event_type_id": 3, "discipline_ids": [7]
    }]"""
    candidate = parse_candidates(reply, "", None)[0]

    assert (candidate.title, candidate.title_kk, candidate.title_en) == (
        "Early Bird Coffee Ride",
        "Erte Coffee Ride",
        "Early Bird Coffee Ride",
    )
    assert candidate.description_kk and candidate.description_en
    assert candidate.venue_kk and candidate.venue_en
    assert candidate.source_url == "https://www.instagram.com/p/Abc123/"
    assert (candidate.city, candidate.country, candidate.date_start) == ("Almaty", "KZ", "2026-08-08")


def test_an_account_that_cannot_be_read_is_reported_not_silently_empty():
    from instagram_agent.fetch import AccountUnavailableError

    source = as_source(Account("gone"))

    def refuse(_source):
        raise AccountUnavailableError("not a professional account")

    report = run_pipeline(
        [source],
        KnownEvents(),
        fetch=refuse,
        extract=lambda text, s: [],
        create=lambda c: None,
        max_events=10,
        dry_run=True,
        today=TODAY,
    )
    assert report.accepted == []
    assert [ref for ref, _ in report.skipped_sources] == ["@gone"]
    assert "professional" in report.skipped_sources[0][1]


def test_the_guidance_is_this_agents_own_and_wants_club_rides():
    """The events agent's guidance says to skip club and social rides -- the opposite of the job.

    Pointing this agent at that file would make every run propose nothing, and the run would look
    healthy while doing it.
    """
    from instagram_agent.run import _GUIDANCE_FILE, _read

    assert _GUIDANCE_FILE.name == "guidance.md"
    assert _GUIDANCE_FILE.parent.name == "instagram_agent"
    guidance = _read(_GUIDANCE_FILE)
    assert "Club rides and group rides" in guidance
    assert "coffee rides" in guidance
