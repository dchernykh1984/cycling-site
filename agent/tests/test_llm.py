from agent.llm import _KIND_GUIDANCE, _SYSTEM, _prompt
from agent.models import KnownEvents, Source, Taxonomy


def _prompt_for(source: Source) -> str:
    return _prompt("body text", source, guidance="", known=KnownEvents(), taxonomy=Taxonomy())


def test_prompt_includes_aggregator_framing_and_hint():
    src = Source("aggregator", "ref", "https://battistrada.com/cal/", hint="use each race's own page")
    out = _prompt_for(src)
    assert "Source type (aggregator)" in out
    assert "AGGREGATOR" in out  # the aggregator-specific instruction
    assert "Source-specific hint: use each race's own page" in out


def test_prompt_pushes_full_calendar_extraction():
    # Aggregator framing tells the model to enumerate every row; the system prompt explains that a
    # month heading + a row's day number is a real date (the fix for terse calendars like bike-events).
    assert "row by row" in _prompt_for(Source("aggregator", "r", "https://cal.kz/"))
    assert "heading" in _SYSTEM


def test_prompt_organizer_and_public_channel_have_distinct_framing():
    organizer = _prompt_for(Source("organizer", "r", "https://athletex.kz/"))
    channel = _prompt_for(Source("tg_public", "r", "https://t.me/s/kztime"))
    assert "ORGANIZER" in organizer and "TELEGRAM" not in organizer
    assert "TELEGRAM" in channel and "ORGANIZER" not in channel


def test_prompt_without_hint_omits_the_hint_line():
    assert "Source-specific hint:" not in _prompt_for(Source("organizer", "r", "https://x.kz/"))


def test_kind_guidance_covers_exactly_the_fetchable_kinds():
    assert set(_KIND_GUIDANCE) == {"aggregator", "organizer", "tg_public"}


def test_system_prompts_do_not_narrow_the_brief_to_cycling():
    """guidance.md widened the brief to running, triathlon and skiing; the system turn must agree.

    The guidance and the per-source hints ride in the user turn. A system prompt asking for cycling
    only contradicts them -- with a running calendar as the source, that conflict resolves to an
    empty extraction.
    """
    from agent.llm import _ENRICH_SYSTEM, _SYSTEM

    for prompt in (_SYSTEM, _ENRICH_SYSTEM):
        assert "cycling competitions from" not in prompt
        assert "ONE cycling event" not in prompt
    assert "running" in _SYSTEM and "triathlon" in _SYSTEM


def test_system_prompt_explains_that_links_are_listed_under_their_name():
    # The names are what let a race be matched to its own page; without saying they are there,
    # the model has no reason to look for them.
    assert '"name - url"' in _SYSTEM
    assert "which race a link belongs to" in _SYSTEM


def test_aggregator_guidance_asks_only_for_a_link_that_can_exist():
    # A calendar's listing page links each race's own entry, but not the organizer's site, so
    # demanding the organizer's page outright left the model with nothing to pick and it gave up.
    guidance = _KIND_GUIDANCE["aggregator"]
    assert "otherwise the race's own entry page on this calendar" in guidance
    assert "leave source_url" in guidance  # empty beats pointing at the listing


def test_aggregator_guidance_still_forbids_the_listing_url():
    assert "NEVER" in _KIND_GUIDANCE["aggregator"]
    assert "listing URL" in _KIND_GUIDANCE["aggregator"]


def test_enrichment_moves_a_calendar_entry_to_the_organizers_page():
    from agent.llm import _ENRICH_SYSTEM

    assert "organizer's own page for this race" in _ENRICH_SYSTEM
    assert "second-hand copy" in _ENRICH_SYSTEM  # says why, so the rule is not cargo-culted
