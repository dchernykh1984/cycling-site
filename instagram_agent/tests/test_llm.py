"""What the model is told. These rules are the difference between a calendar and a photo album."""

from agent.models import KnownEvents, Taxonomy
from instagram_agent.accounts import Account
from instagram_agent.llm import _SYSTEM, build_prompt


def _known():
    known = KnownEvents()
    known.existing.append(
        {"title": "Early Bird Ride 26 July", "titles": ["Early Bird Ride 26 July"], "date_start": "2026-07-26"}
    )
    known.rejected.append(
        {"title": "A photo report", "titles": ["A photo report"], "date_start": "2026-07-20", "reason": "not an event"}
    )
    return known


def test_the_model_is_told_to_take_announcements_and_leave_reports():
    """The feed is mostly reports; taking them would fill the calendar with rides already ridden."""
    assert "ONLY ANNOUNCEMENTS" in _SYSTEM
    assert "already happened" in _SYSTEM
    assert "photo report" in _SYSTEM


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


def test_no_link_and_no_platform_may_reach_a_published_event():
    """The site's maintainer must not publish the platform's name or a link into it -- see
    instagram_agent/attribution.py. The prompt is the first of two guards; the code is the one that
    holds."""
    assert "NO LINKS AND NO PLATFORM" in _SYSTEM
    assert "Do not output source_url" in _SYSTEM
    assert "never " in _SYSTEM and "name the website or app" in _SYSTEM
    assert "source_url" not in _SYSTEM.split("NO LINKS AND NO PLATFORM")[0], "the schema must not ask for it"


def test_the_prompt_carries_the_taxonomy_and_what_the_site_already_knows():
    taxonomy = Taxonomy(event_types=[{"id": 3, "name": "Ride"}], disciplines=[{"id": 7, "name": "Road"}])
    prompt = build_prompt("posts here", Account("ubtalmaty"), "guidance text", _known(), taxonomy, "2026-08-01")
    assert "3=Ride" in prompt and "7=Road" in prompt
    assert "Early Bird Ride 26 July" in prompt
    assert "A photo report" in prompt and "not an event" in prompt
    assert "guidance text" in prompt
    assert "posts here" in prompt


def test_the_prompt_says_a_weekly_ride_repeats_rather_than_duplicates():
    """Without this the known list reads as "never propose an Early Bird Ride again"."""
    prompt = build_prompt("", Account("ubtalmaty"), "", _known(), Taxonomy(), "2026-08-01")
    assert "NEW event" in prompt
    assert "SAME DAY" in prompt


def test_the_prompt_works_with_nothing_known_yet():
    prompt = build_prompt("posts", Account("ubtalmaty"), "", KnownEvents(), Taxonomy(), "2026-08-01")
    assert "(none)" in prompt
