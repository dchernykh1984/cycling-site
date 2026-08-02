"""The run itself: wiring channels into the shared pipeline, and what may never leak out of it."""

import datetime

from agent.models import Candidate, KnownEvents, RunReport
from agent.pipeline import run_pipeline
from telegram_agent.channels import Channel
from telegram_agent.run import _MAX_PER_CHANNEL, _scrubbed, _with_channel_city, as_source, summary

TODAY = datetime.date(2026, 8, 2)


def _candidate(title="Saturday Ride", date="2026-08-08", **kwargs):
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
        max_per_source=_MAX_PER_CHANNEL,
        dry_run=dry_run,
        today=TODAY,
    )
    return report, created


def test_a_channel_becomes_a_source_the_shared_pipeline_will_read():
    """A missing fetch_url means "skip this source" to the pipeline, so it must be present."""
    source = as_source(Channel(ref="+abc", hint="a club chat"))
    assert source.kind == "telegram"
    assert source.ref == "+abc"
    assert source.fetch_url == "https://t.me/+abc"
    assert source.hint == "a club chat"
    assert as_source(Channel(ref="@almatyriders")).fetch_url == "https://t.me/almatyriders"
    assert as_source(Channel(ref="c/1949598843")).fetch_url == "https://t.me/c/1949598843"


def test_the_limit_caps_how_many_events_one_run_proposes():
    source = as_source(Channel(ref="@almatyriders"))
    many = [_candidate(title=f"Ride {n}", date=f"2026-08-{n + 10:02d}") for n in range(8)]
    report, created = _run([source], {source.ref: many}, max_events=3)
    assert len(report.accepted) == 3
    assert report.capped is True
    assert len(created) == 3


def test_one_talkative_channel_cannot_spend_the_whole_budget():
    chatty = as_source(Channel(ref="@chatty"))
    quiet = as_source(Channel(ref="@quiet"))
    flood = [_candidate(title=f"Ride {n}", date=f"2026-08-{n + 10:02d}") for n in range(8)]
    one = [_candidate(title="The one ride", date="2026-08-25")]
    report, _ = _run([chatty, quiet], {chatty.ref: flood, quiet.ref: one}, max_events=10)
    assert report.proposed_by_source[chatty.ref] == _MAX_PER_CHANNEL
    assert report.proposed_by_source[quiet.ref] == 1


def test_a_dry_run_proposes_without_posting_anything():
    source = as_source(Channel(ref="+abc"))
    report, created = _run([source], {source.ref: [_candidate()]}, dry_run=True)
    assert [c.title for c in report.accepted] == ["Saturday Ride"]
    assert created == []


def test_a_ride_with_no_city_takes_the_one_the_channel_was_given():
    channel = Channel(ref="+abc", city="Almaty")
    placed = _with_channel_city(_candidate(), channel)
    assert (placed.city, placed.city_en) == ("Almaty", "Almaty")


def test_a_ride_that_names_its_own_city_keeps_it():
    channel = Channel(ref="+abc", city="Almaty")
    assert _with_channel_city(_candidate(city="Talgar"), channel).city == "Talgar"


def test_nothing_pointing_back_at_the_channel_survives_scrubbing():
    """The model is told not to write these; this is the guard that holds when it does anyway."""
    candidate = _candidate(
        source_url="https://t.me/c/1949598843/5",
        url_route="https://t.me/+abc",
        url_registration="https://t.me/somebot",
    )
    scrubbed = _scrubbed(candidate)
    assert scrubbed.source_url == ""
    assert scrubbed.url_route == ""
    assert scrubbed.url_registration == ""


def test_an_external_registration_link_from_the_announcement_survives():
    scrubbed = _scrubbed(_candidate(url_registration="https://forms.gle/abc123"))
    assert scrubbed.url_registration == "https://forms.gle/abc123"


def test_a_channel_link_written_into_the_text_is_scrubbed_too():
    """A t.me link in a description discloses the private source as surely as one in source_url."""
    candidate = Candidate(
        title="Ride (telegram.me/+abc)",
        date_start="2026-08-08",
        description="<p>Ride at 7. Details: https://t.me/+AbCdEfGhIjKlMnOp ask there.</p>",
        description_en="<p>See t.me/c/1949598843/5 for the route.</p>",
    )
    scrubbed = _scrubbed(candidate)
    for text in (scrubbed.description, scrubbed.description_en, scrubbed.title):
        assert "t.me" not in text
        assert "AbCdEfGhIjKlMnOp" not in text
    assert "Ride at 7." in scrubbed.description, "the announcement itself survives"


def test_the_summary_names_each_proposal_and_its_place_but_never_a_channel_link():
    report = RunReport(dry_run=True)
    report.accepted.append(_candidate(city="Almaty", venue="Halyk Bank car park", country="KZ"))
    report.skipped_sources.append(("+abc", "the invite link has expired or was revoked"))
    report.extracted.append(("+abc", 0))
    report.extracted.append(("@almatyriders", 4))
    report.proposed_by_source["@almatyriders"] = 1
    out = summary(report)
    assert "would propose: 1" in out
    assert "place: KZ / Almaty / Halyk Bank car park" in out
    assert "channel unreadable: +abc (the invite link has expired or was revoked)" in out
    assert "@almatyriders: 4 extracted, 1 proposed" in out
    assert "t.me" not in out


def test_an_unreadable_channel_is_reported_not_fatal():
    """One expired invite must not cost the night for the channels after it."""

    def _fetch(source):
        if source.ref == "+dead":
            raise RuntimeError("the invite link has expired or was revoked")
        return "text"

    good = as_source(Channel(ref="@alive"))
    report = run_pipeline(
        [as_source(Channel(ref="+dead")), good],
        KnownEvents(),
        fetch=_fetch,
        extract=lambda text, s: [_candidate()] if s.ref == "@alive" else [],
        create=lambda c: None,
        max_events=10,
        dry_run=False,
        today=TODAY,
    )
    assert [ref for ref, _ in report.skipped_sources] == ["+dead"]
    assert len(report.accepted) == 1


def test_missing_telegram_credentials_end_the_run_cleanly(monkeypatch, capsys):
    """Before the service account exists, a scheduled run must report and exit 0 -- not fail red."""
    from telegram_agent import run as module

    for name in ("TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_SESSION"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SITE_BASE_URL", "https://example.kz")
    monkeypatch.setenv("AGENT_API_TOKEN", "t")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example")
    assert module.main() == 0
    out = capsys.readouterr().out
    assert "Telegram credentials not set" in out
    assert "TELEGRAM_SESSION" in out


def test_a_revoked_session_fails_with_its_own_message_not_a_traceback(monkeypatch, capsys):
    """The message says how to fix it (mint a new session); a traceback would bury that."""
    from telegram_agent import fetch as fetch_module
    from telegram_agent import run as module

    monkeypatch.setenv("SITE_BASE_URL", "https://example.kz")
    monkeypatch.setenv("AGENT_API_TOKEN", "t")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example")
    monkeypatch.setenv("TELEGRAM_API_ID", "1")
    monkeypatch.setenv("TELEGRAM_API_HASH", "h")
    monkeypatch.setenv("TELEGRAM_SESSION", "revoked")

    def _refused(api_id, api_hash, session):
        raise fetch_module.ChannelUnavailableError("the Telegram session is not authorized")

    monkeypatch.setattr(module, "_what_the_site_knows", lambda client: (KnownEvents(), None, []))
    monkeypatch.setattr(module.fetch, "open_client", _refused)
    assert module.main() == 1
    assert "not authorized" in capsys.readouterr().err
