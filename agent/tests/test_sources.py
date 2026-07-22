from agent.sources import parse_sources


def test_aggregator_and_organizer_kinds():
    result = parse_sources(
        "aggregators:\n  - https://battistrada.com/en/cycling-calendar/\norganizers:\n  - https://changan-race.kz/ru/\n"
    )
    by_url = {s.fetch_url: s.kind for s in result}
    assert by_url["https://battistrada.com/en/cycling-calendar/"] == "aggregator"
    assert by_url["https://changan-race.kz/ru/"] == "organizer"


def test_mapping_entry_carries_hint_and_can_be_disabled():
    result = parse_sources(
        "organizers:\n"
        '  - url: https://athletex.kz/\n    hint: "races under /competitions"\n'
        "  - url: https://paused.kz/\n    enabled: false\n"
    )
    assert len(result) == 1  # the disabled one is dropped
    assert result[0].fetch_url == "https://athletex.kz/"
    assert result[0].hint == "races under /competitions"


def test_public_channel_from_handle_and_post_link():
    result = parse_sources("telegram_public:\n  - '@roadcyclingkz'\n  - https://t.me/mystartkz/903\n")
    urls = {s.fetch_url for s in result}
    assert urls == {"https://t.me/s/roadcyclingkz", "https://t.me/s/mystartkz"}  # post id dropped
    assert all(s.kind == "tg_public" for s in result)


def test_private_telegram_marked_unfetchable():
    result = parse_sources("telegram_private:\n  - https://t.me/+3mTEnASuHG40MTRi\n  - https://t.me/c/1949598843/1\n")
    assert len(result) == 2
    assert all(s.kind == "tg_private" and s.fetch_url is None for s in result)


def test_account_section_needs_account_and_is_distinct_from_private():
    # Public groups/users: no invite, but unreadable without an account -> own kind, not fetchable.
    result = parse_sources("telegram_account:\n  - '@almatyriders'\n  - https://t.me/talgar2026\n")
    assert len(result) == 2
    assert all(s.kind == "tg_account" and s.fetch_url is None for s in result)


def test_channel_ref_from_preview_url_and_query_string():
    result = parse_sources("telegram_public:\n  - https://t.me/s/kztime\n  - https://t.me/roadcyclingkz?si=1\n")
    assert {s.fetch_url for s in result} == {"https://t.me/s/kztime", "https://t.me/s/roadcyclingkz"}


def test_private_looking_link_in_public_section_is_treated_as_private():
    # Defensive: an invite/internal link mistakenly filed under telegram_public is still unreadable.
    result = parse_sources("telegram_public:\n  - https://t.me/+secretinvite\n")
    assert len(result) == 1
    assert result[0].kind == "tg_private" and result[0].fetch_url is None


def test_duplicate_channel_across_forms_deduped():
    result = parse_sources("telegram_public:\n  - '@velokz'\n  - https://t.me/velokz\n")
    assert len(result) == 1
    assert result[0].fetch_url == "https://t.me/s/velokz"


def test_empty_or_missing_sections_yield_no_sources():
    assert parse_sources("") == []
    assert parse_sources("aggregators:\norganizers: []\n") == []


def test_malformed_top_level_yields_no_sources_without_crashing():
    # A maintainer editing the YAML could leave a bare list / scalar at the top level.
    assert parse_sources("- https://a.kz/\n- https://b.kz/\n") == []
    assert parse_sources("just a string") == []


def test_local_sources_are_scanned_before_the_big_foreign_calendars():
    """The run stops at its quota, so section order is what enforces the geography ladder.

    The aggregators are Russian and worldwide calendars with dozens of upcoming rows; scanning them
    first would spend every nightly slot before a Kazakh or Kyrgyz source was ever fetched.
    """
    yaml = """
aggregators:
  - https://begaem.com/blizhayshie-startyi-v-rossii
organizers:
  - https://changan-race.kz/ru/
telegram_public:
  - https://t.me/roadcyclingkz
"""
    kinds = [source.kind for source in parse_sources(yaml)]
    assert kinds == ["organizer", "tg_public", "aggregator"]


def test_real_sources_file_puts_every_local_source_first():
    from pathlib import Path

    sources = parse_sources(Path("events_sources.yaml").read_text())
    first_aggregator = next(i for i, s in enumerate(sources) if s.kind == "aggregator")
    local = [i for i, s in enumerate(sources) if s.kind in ("organizer", "tg_public")]
    assert max(local) < first_aggregator
