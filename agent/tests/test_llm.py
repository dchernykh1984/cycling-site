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
