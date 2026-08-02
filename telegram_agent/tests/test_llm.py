"""What the model is told. A chat is a conversation; these rules pull the announcements out of it."""

from agent.models import KnownEvents, Taxonomy
from telegram_agent.channels import Channel
from telegram_agent.llm import _SYSTEM, build_prompt


def _known():
    known = KnownEvents()
    known.existing.append(
        {"title": "Saturday Ride 26 July", "titles": ["Saturday Ride 26 July"], "date_start": "2026-07-26"}
    )
    known.rejected.append(
        {"title": "A photo report", "titles": ["A photo report"], "date_start": "2026-07-20", "reason": "not an event"}
    )
    return known


def test_the_model_is_told_to_take_announcements_and_leave_the_conversation():
    """A group chat is mostly talk; a reply about a ride must not become a second ride."""
    assert "ONLY ANNOUNCEMENTS" in _SYSTEM
    assert "already happened" in _SYSTEM or "already took place" in _SYSTEM
    assert "not a second" in _SYSTEM


def test_the_model_is_told_to_resolve_a_relative_date_against_the_publication_date():
    assert "publication date" in _SYSTEM
    assert "this Saturday" in _SYSTEM
    assert "not guessing" in _SYSTEM


def test_the_model_is_told_not_to_invent_a_date_it_cannot_read():
    assert "omit the event rather than" in _SYSTEM
    assert "already in the past, omit it" in _SYSTEM


def test_every_locale_is_required():
    assert "all three locales" in _SYSTEM
    for locale in ("ru (Russian)", "kk (Kazakh)", "en (English)"):
        assert locale in _SYSTEM


def test_the_source_may_never_be_named():
    """The channels are private; the site must not disclose where an announcement was read.
    The prompt is the first of two guards; run._scrubbed is the one that holds."""
    assert "NEVER NAME THE SOURCE" in _SYSTEM
    assert "Do not output source_url" in _SYSTEM
    assert "no attribution at all" in _SYSTEM
    assert "never a t.me link" in _SYSTEM


def test_the_prompt_carries_the_guidance_the_known_events_and_the_taxonomy():
    taxonomy = Taxonomy(event_types=[{"id": 1, "name": "ride"}], disciplines=[{"id": 2, "name": "road"}])
    prompt = build_prompt(
        "Telegram channel: +abc",
        Channel(ref="+abc"),
        "propose kids' starts",
        _known(),
        taxonomy,
        today="2026-08-02",
    )
    assert "propose kids' starts" in prompt
    assert "Saturday Ride 26 July (2026-07-26)" in prompt
    assert "A photo report (2026-07-20): not an event" in prompt
    assert "1=ride" in prompt
    assert "2=road" in prompt
    assert prompt.rstrip().endswith("Telegram channel: +abc")


def test_a_weekly_ride_is_a_new_event_each_week():
    prompt = build_prompt("text", Channel(ref="+abc"), "", _known(), Taxonomy(), today="2026-08-02")
    assert "NEW event each week" in prompt
    assert "SAME DAY" in prompt
