"""The run itself: wiring channels into the shared pipeline, and what may never leak out of it."""

import datetime

from agent.models import Candidate, KnownEvents, RunReport, Taxonomy
from agent.pipeline import run_pipeline
from telegram_agent.channels import Channel
from telegram_agent.run import _scrubbed, _with_channel_city, as_source, summary

_PER_CHANNEL = 5

TODAY = datetime.date(2026, 8, 2)


def _config(**overrides):
    from telegram_agent.config import Config

    settings = {
        "site_base_url": "https://example.kz",
        "api_token": "t",
        "llm_api_key": "k",
        "llm_base_url": "https://llm.example",
        "llm_model": "m",
        "telegram_api_id": 1,
        "telegram_api_hash": "h",
        "telegram_session": "s",
        "max_events": 10,
        "max_per_channel": _PER_CHANNEL,
        "recent_hours": 25,
        "max_posts": 1000,
        "dry_run": True,
    }
    return Config(**{**settings, **overrides})


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
        max_per_source=_PER_CHANNEL,
        dry_run=dry_run,
        today=TODAY,
    )
    return report, created


def test_a_channel_becomes_a_source_the_shared_pipeline_will_read():
    """A missing fetch_url means "skip this source"; a pseudo-scheme satisfies that without ever
    baking a web domain into an agent that talks MTProto and would not notice t.me being down."""
    source = as_source(Channel(ref="+abc", hint="a club chat"))
    assert source.kind == "telegram"
    assert source.ref == "+abc"
    assert source.fetch_url == "mtproto:+abc"
    assert source.hint == "a club chat"
    assert as_source(Channel(ref="c/1949598843")).fetch_url == "mtproto:c/1949598843"


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
    assert report.proposed_by_source[chatty.ref] == _PER_CHANNEL
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


def test_the_workflow_hands_the_run_every_name_the_config_reads():
    """The two are tied only by env names; a typo on either side silently falls back to a default."""
    from pathlib import Path

    workflow = Path(".github/workflows/telegram-agent.yml").read_text(encoding="utf-8")
    for name in (
        "SITE_BASE_URL",
        "AGENT_API_TOKEN",
        "LLM_API_KEY",
        "LLM_BASE_URL",
        "LLM_MODEL",
        "TELEGRAM_API_ID",
        "TELEGRAM_API_HASH",
        "TELEGRAM_SESSION",
        "TELEGRAM_MAX_EVENTS",
        "TELEGRAM_MAX_PER_CHANNEL",
        "TELEGRAM_RECENT_HOURS",
        "TELEGRAM_MAX_POSTS",
        "TELEGRAM_DRY_RUN",
    ):
        assert f"{name}:" in workflow, f"the workflow never sets {name}"
    assert "python -m telegram_agent.run" in workflow
    assert "telethon" in workflow, "the runner must install the one dependency the site does not carry"


def test_the_guidance_is_this_agents_own_and_wants_more_than_rides():
    """This agent reads mountain and running communities as well as cycling clubs.

    Nothing else pins this file: reverting it to a cycling-only text leaves every test green while
    the nightly run quietly stops proposing hikes -- which is the half of the job the mountain
    channel was added for. Keywords only, so the file stays freely hand-editable.
    """
    from telegram_agent.run import _GUIDANCE_FILE, _read

    guidance = _read(_GUIDANCE_FILE)
    assert guidance, "the agent ships its own guidance file"
    assert "not cycling-only" in guidance
    assert "Hikes, walks and ascents" in guidance
    assert "Runs and ski outings" in guidance
    assert "Club rides and group rides" in guidance, "the cycling half must survive too"


def test_a_run_reports_how_deep_it_read_each_channel(capsys):
    """The visibility line only helps if the run actually emits it -- and nothing else calls it.

    Drives the real _run (not the pipeline directly) with a stub Telegram client, so the wiring
    between reading a channel and printing what was read is exercised end to end.
    """
    import datetime

    from telegram_agent import run as module
    from telegram_agent.fetch import Message

    today = datetime.date.today()
    messages = [Message(text="an announcement worth reading", published=today)] * 2
    prompts: list[str] = []

    def _record(text, *args, **kwargs):
        prompts.append(text)
        return "[]"

    original_read, original_extract = module.fetch.read_messages, module.llm.extract_raw
    try:
        module.fetch.read_messages = lambda client, channel, hours, cap: ("A club", messages, False)
        module.llm.extract_raw = _record
        module._run(
            _config(),
            [Channel(ref="@almatyriders", city="Almaty")],
            client=None,
            telegram=None,
            known=KnownEvents(),
            taxonomy=Taxonomy(),
            tree=[],
        )
    finally:
        module.fetch.read_messages, module.llm.extract_raw = original_read, original_extract
    out = capsys.readouterr().out
    assert "read 2 messages of the last 25h" in out
    assert len(prompts) == 1, "a quiet channel is a single prompt"


def test_a_channel_with_more_than_a_promptful_is_read_in_several_prompts():
    """Ten days of a busy chat must not become one prompt: the announcement would drown in it."""
    import datetime

    from telegram_agent import run as module
    from telegram_agent.fetch import MESSAGES_PER_PROMPT, Message

    today = datetime.date.today()
    messages = [Message(text=f"message number {n} in the chat", published=today) for n in range(250)]
    prompts: list[str] = []

    def _record(text, *args, **kwargs):
        prompts.append(text)
        return "[]"

    original_read, original_extract = module.fetch.read_messages, module.llm.extract_raw
    try:
        module.fetch.read_messages = lambda client, channel, hours, cap: ("A club", messages, True)
        module.llm.extract_raw = _record
        module._run(
            _config(recent_hours=250),
            [Channel(ref="@chatty")],
            client=None,
            telegram=None,
            known=KnownEvents(),
            taxonomy=Taxonomy(),
            tree=[],
        )
    finally:
        module.fetch.read_messages, module.llm.extract_raw = original_read, original_extract
    assert len(prompts) == 3, f"250 messages at {MESSAGES_PER_PROMPT} per prompt"
    seen = "\n".join(prompts)
    for n in (0, 99, 100, 249):
        assert f"message number {n} in the chat" in seen, f"message {n} never reached the model"


def test_every_batch_of_a_channel_contributes_its_events():
    """Candidates from a later batch must not be dropped on the floor."""
    import datetime

    from telegram_agent import run as module
    from telegram_agent.fetch import Message

    today = datetime.date.today()
    messages = [Message(text=f"message number {n} in the chat", published=today) for n in range(150)]
    replies = iter(
        [
            '[{"title": {"ru": "First"}, "date_start": "2026-08-08", "description": {"ru": "d"}}]',
            '[{"title": {"ru": "Second"}, "date_start": "2026-08-09", "description": {"ru": "d"}}]',
        ]
    )
    original_read, original_extract = module.fetch.read_messages, module.llm.extract_raw
    try:
        module.fetch.read_messages = lambda client, channel, hours, cap: ("A club", messages, False)
        module.llm.extract_raw = lambda *args, **kwargs: next(replies)
        out = module._run(
            _config(),
            [Channel(ref="@chatty")],
            client=None,
            telegram=None,
            known=KnownEvents(),
            taxonomy=Taxonomy(),
            tree=[],
        )
    finally:
        module.fetch.read_messages, module.llm.extract_raw = original_read, original_extract
    assert "First" in out
    assert "Second" in out
