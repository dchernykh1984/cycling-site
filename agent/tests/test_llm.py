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
