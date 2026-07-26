import datetime
from dataclasses import replace

from agent.models import Candidate, KnownEvents, Source, Taxonomy
from agent.pipeline import normalize_key, parse_candidates, run_pipeline

TODAY = datetime.date(2026, 7, 1)


def _src(url="https://x.kz"):
    return Source("organizer", url, url)


def _run(sources, by_source, *, known=None, max_events=10, dry_run=False, max_per_source=0):
    created = []
    report = run_pipeline(
        sources,
        known or KnownEvents(),
        fetch=lambda s: "text",
        extract=lambda text, s: by_source.get(s.fetch_url, []),
        create=created.append,
        max_events=max_events,
        dry_run=dry_run,
        today=TODAY,
        max_per_source=max_per_source,
    )
    return report, created


def test_normalize_key_ignores_case_and_punctuation():
    assert normalize_key("Gran Fondo, Almaty!", "2026-08-01") == normalize_key("gran  fondo almaty", "2026-08-01")


def test_parse_candidates_plain_json():
    raw = '[{"title": "Race A", "date_start": "2026-08-01", "description": "d"}]'
    result = parse_candidates(raw, "https://s")
    assert len(result) == 1
    assert result[0].title == "Race A"
    assert result[0].source_url == "https://s"


def test_parse_candidates_code_fence_and_prose():
    raw = 'Here you go:\n```json\n[{"title": "R", "date_start": "2026-08-01"}]\n```'
    assert len(parse_candidates(raw)) == 1


def test_parse_candidates_malformed_or_incomplete_is_dropped():
    assert parse_candidates("not json at all") == []
    assert parse_candidates('[{"title": "", "date_start": "2026-08-01"}]') == []
    assert parse_candidates('[{"title": "X"}]') == []  # no date


def test_parse_candidates_extracts_type_and_disciplines():
    raw = '[{"title": "R", "date_start": "2026-08-01", "event_type_id": 1, "discipline_ids": [9, 24]}]'
    candidate = parse_candidates(raw)[0]
    assert candidate.event_type_id == 1
    assert candidate.discipline_ids == [9, 24]


def test_parse_candidates_extracts_location_fields():
    raw = (
        '[{"title": "R", "date_start": "2026-08-01", "country": "Kazakhstan", "region": "Almaty region",'
        ' "city": "Almaty", "venue": "Medeu", "lat": 43.16, "lng": "76.98"}]'
    )
    candidate = parse_candidates(raw)[0]
    assert candidate.city == "Almaty"
    assert candidate.venue == "Medeu"
    assert candidate.country == "Kazakhstan"
    assert candidate.lat == 43.16
    assert candidate.lng == 76.98  # parsed from a string too


def test_parse_candidates_localized_title_description_venue():
    raw = (
        '[{"title": {"ru": "race-ru", "kk": "race-kk", "en": "race-en"}, "date_start": "2026-08-01",'
        ' "description": {"ru": "desc-ru", "kk": "desc-kk", "en": "desc-en"},'
        ' "city": "Almaty", "venue": {"ru": "venue-ru", "kk": "venue-kk", "en": "venue-en"}}]'
    )
    candidate = parse_candidates(raw)[0]
    assert (candidate.title, candidate.title_kk, candidate.title_en) == ("race-ru", "race-kk", "race-en")
    assert (candidate.description, candidate.description_en) == ("desc-ru", "desc-en")
    assert (candidate.venue, candidate.venue_kk, candidate.venue_en) == ("venue-ru", "venue-kk", "venue-en")


def test_parse_candidates_plain_string_title_is_ru_only():
    candidate = parse_candidates('[{"title": "Race", "date_start": "2026-08-01"}]')[0]
    assert candidate.title == "Race"
    assert candidate.title_kk == ""
    assert candidate.title_en == ""


def test_parse_candidates_keeps_an_english_only_title_by_backfilling_ru():
    """A foreign race titled only in English must not be dropped for an empty ru field."""
    candidate = parse_candidates(
        '[{"title": {"ru": "", "kk": "", "en": "Reykjavik Marathon"}, "date_start": "2026-08-22"}]'
    )[0]
    assert candidate.title == "Reykjavik Marathon"  # ru backfilled from en
    assert candidate.title_en == "Reykjavik Marathon"


def test_parse_candidates_salvages_a_reply_truncated_at_the_token_limit():
    """A dense calendar reply cut off mid-object must still yield the events that came through whole."""
    raw = (
        '```json\n[{"title": "Race A", "date_start": "2026-08-01"}, '
        '{"title": "Race B", "date_start": "2026-08-02"}, '
        '{"title": "Race C", "date_start": "2026-08-03", "description": {"ru": "cut off he'  # truncated tail
    )
    titles = [c.title for c in parse_candidates(raw)]
    assert titles == ["Race A", "Race B"]  # the two complete objects survive; the broken tail is dropped


def test_parse_candidates_extracts_route_and_registration_urls():
    raw = (
        '[{"title": "R", "date_start": "2026-08-01", "url_route": "https://strava.com/routes/1",'
        ' "url_registration": "https://reg.example.kz"}]'
    )
    candidate = parse_candidates(raw)[0]
    assert candidate.url_route == "https://strava.com/routes/1"
    assert candidate.url_registration == "https://reg.example.kz"


def test_parse_candidates_missing_location_fields_default_empty():
    candidate = parse_candidates('[{"title": "R", "date_start": "2026-08-01"}]')[0]
    assert candidate.city == ""
    assert candidate.lat is None


def test_parse_candidates_drops_taxonomy_ids_not_on_the_site():
    taxonomy = Taxonomy(event_types=[{"id": 1, "name": "Race"}], disciplines=[{"id": 9, "name": "Road"}])
    raw = '[{"title": "R", "date_start": "2026-08-01", "event_type_id": 99, "discipline_ids": [9, 77]}]'
    candidate = parse_candidates(raw, taxonomy=taxonomy)[0]
    assert candidate.event_type_id is None  # 99 is not a real event type -> dropped
    assert candidate.discipline_ids == [9]  # 77 dropped, 9 kept


def test_proposes_new_valid_events():
    src = _src()
    cands = [Candidate("Race A", "2026-08-01"), Candidate("Race B", "2026-09-01")]
    report, created = _run([src], {src.fetch_url: cands})
    assert len(report.accepted) == 2
    assert len(created) == 2


def test_skips_known_and_previously_rejected():
    src = _src()
    known = KnownEvents(
        existing_keys={normalize_key("Race A", "2026-08-01")},
        rejected=[
            {
                "key": normalize_key("Race B", "2026-09-01"),
                "title": "Race B",
                "date_start": "2026-09-01",
                "reason": "dup",
            }
        ],
    )
    cands = [Candidate("Race A", "2026-08-01"), Candidate("Race B", "2026-09-01"), Candidate("Race C", "2026-10-01")]
    report, _ = _run([src], {src.fetch_url: cands}, known=known)
    assert [c.title for c in report.accepted] == ["Race C"]


def test_skips_fuzzy_duplicate_of_existing_event():
    src = _src()
    known = KnownEvents(existing=[{"title": "Apricot Marathon Gravel MTB 2026", "date_start": "2026-08-09"}])
    cands = [Candidate("Apricot Marathon Gravel MTB Race 2026", "2026-08-09")]
    report, created = _run([src], {src.fetch_url: cands}, known=known)
    assert report.accepted == []
    assert created == []
    assert any("near-duplicate" in reason for _, reason in report.skipped_candidates)


def test_skips_cross_language_duplicate_of_existing_event():
    src = _src()
    known = KnownEvents(
        existing=[{"title": "Apricot Marathon Gravel MTB 2026", "date_start": "2026-08-09"}]  # stored in English
    )
    # Proposal is in Russian, but its en translation matches the existing English event.
    cand = Candidate("Aprikot Marafon 2026", "2026-08-09", title_en="Apricot Marathon Gravel MTB Race 2026")
    report, created = _run([src], {src.fetch_url: [cand]}, known=known)
    assert report.accepted == []
    assert created == []


def test_skips_fuzzy_duplicate_found_across_sources_in_one_run():
    src = _src()
    cands = [
        Candidate("Apricot Marathon Gravel MTB 2026", "2026-08-09"),
        Candidate("Apricot Marathon Gravel MTB Race 2026", "2026-08-09"),  # same event, worded differently
    ]
    report, _ = _run([src], {src.fetch_url: cands})
    assert [c.title for c in report.accepted] == ["Apricot Marathon Gravel MTB 2026"]


def test_skips_past_and_bad_dates():
    src = _src()
    cands = [Candidate("Old", "2026-06-01"), Candidate("Bad", "not-a-date"), Candidate("New", "2026-08-01")]
    report, _ = _run([src], {src.fetch_url: cands})
    assert [c.title for c in report.accepted] == ["New"]


def test_cap_limits_total_proposals():
    src = _src()
    cands = [Candidate(f"Race {i}", "2026-08-01") for i in range(5)]
    report, created = _run([src], {src.fetch_url: cands}, max_events=2)
    assert len(report.accepted) == 2
    assert report.capped is True
    assert len(created) == 2


def test_enrich_is_applied_to_accepted_candidates():
    src = _src()
    created = []
    report = run_pipeline(
        [src],
        KnownEvents(),
        fetch=lambda s: "t",
        extract=lambda text, s: [Candidate("Race A", "2026-08-01")],
        create=created.append,
        max_events=10,
        dry_run=False,
        today=TODAY,
        enrich=lambda c: replace(c, description="<p>enriched</p>"),
    )
    assert report.accepted[0].description == "<p>enriched</p>"
    assert created[0].description == "<p>enriched</p>"


def test_enrich_producing_an_invalid_date_is_skipped():
    src = _src()
    report = run_pipeline(
        [src],
        KnownEvents(),
        fetch=lambda s: "t",
        extract=lambda text, s: [Candidate("Race A", "2026-08-01")],
        create=lambda c: None,
        max_events=10,
        dry_run=False,
        today=TODAY,
        enrich=lambda c: replace(c, date_start="2020-01-01"),  # enrichment moved it into the past
    )
    assert report.accepted == []
    assert any("after enrich" in reason for _, reason in report.skipped_candidates)


def test_dry_run_posts_nothing():
    src = _src()
    report, created = _run([src], {src.fetch_url: [Candidate("R", "2026-08-01")]}, dry_run=True)
    assert len(report.accepted) == 1
    assert created == []
    assert report.dry_run is True


def test_private_source_skipped_and_logged():
    report, _ = _run([Source("tg_private", "t.me/+secret")], {})
    assert report.skipped_sources[0][1] == "private Telegram -- needs an invite"
    assert not report.accepted


def test_account_source_skipped_with_its_own_reason():
    report, _ = _run([Source("tg_account", "@almatyriders")], {})
    assert report.skipped_sources[0][1] == "public group/account -- needs a Telegram account"
    assert not report.accepted


def test_fetch_failure_skips_source():
    src = _src()

    def boom(_source):
        raise RuntimeError("network down")

    report = run_pipeline(
        [src],
        KnownEvents(),
        fetch=boom,
        extract=lambda text, s: [Candidate("R", "2026-08-01")],
        create=lambda c: None,
        max_events=10,
        dry_run=False,
        today=TODAY,
    )
    assert report.skipped_sources
    assert not report.accepted


def test_post_error_is_recorded_not_raised():
    src = _src()

    def failing_create(_candidate):
        raise RuntimeError("api down")

    report = run_pipeline(
        [src],
        KnownEvents(),
        fetch=lambda s: "t",
        extract=lambda text, s: [Candidate("R", "2026-08-01")],
        create=failing_create,
        max_events=10,
        dry_run=False,
        today=TODAY,
    )
    assert report.accepted
    assert report.post_errors


def test_report_records_the_per_source_extraction_count():
    """The run must log how many candidates each source's extraction returned, to locate a source
    that silently yields nothing."""
    from agent.models import KnownEvents
    from agent.pipeline import run_pipeline

    src = Source("aggregator", "cal", "https://cal.test/")

    def fetch(source):
        return "text"

    def extract(text, source):
        return [Candidate(title="A", date_start="2026-09-01"), Candidate(title="B", date_start="2026-09-02")]

    report = run_pipeline(
        [src], KnownEvents(), fetch=fetch, extract=extract, create=lambda c: None, max_events=10, dry_run=True
    )
    assert report.extracted == [("cal", 2)]


def _extract_with(kind: str, reply: str):
    """Run agent.run._extract_candidates against a stubbed model reply and return the candidates."""
    from unittest.mock import patch

    from agent import run, sources
    from agent.config import Config
    from agent.models import KnownEvents, Taxonomy

    source = sources.Source(kind=kind, ref="cal", fetch_url="https://bike-events.ru/index.php?season=S2026")
    config = Config(
        site_base_url="https://site.test",
        api_token="t",
        llm_api_key="k",
        llm_base_url="https://llm.test",
        llm_model="m",
        max_events=10,
        max_per_source=5,
        dry_run=True,
    )
    with patch("agent.llm.extract_raw", return_value=reply):
        return run._extract_candidates("page text", source, "", KnownEvents(), Taxonomy(), config)


_ONE_EVENT_NO_LINK = '[{"title": "Dark Race", "date_start": "2026-09-26"}]'


def test_aggregator_listing_url_is_not_used_as_an_events_announcement():
    # Following a calendar's own listing URL lands the reader on dozens of races with no way to
    # tell which one was meant, so an unlinked race is better left without a link.
    (candidate,) = _extract_with("aggregator", _ONE_EVENT_NO_LINK)
    assert candidate.source_url == ""


def test_an_organizers_own_page_still_backs_its_events():
    # On the organizer's own site the fetched page *is* the announcement, so it stays the fallback.
    (candidate,) = _extract_with("organizer", _ONE_EVENT_NO_LINK)
    assert candidate.source_url == "https://bike-events.ru/index.php?season=S2026"


def test_a_link_the_model_found_always_wins():
    reply = '[{"title": "Dark Race", "date_start": "2026-09-26", "source_url": "https://velogearance.ru/tg26/"}]'
    for kind in ("aggregator", "organizer"):
        (candidate,) = _extract_with(kind, reply)
        assert candidate.source_url == "https://velogearance.ru/tg26/"


def _accepted(**kwargs):
    from agent.models import Candidate

    defaults = {"title": "Dark Race", "date_start": "2026-09-26"}
    defaults.update(kwargs)
    return Candidate(**defaults)


def _summary_for(*candidates, dry_run: bool = True) -> str:
    from agent.models import RunReport
    from agent.run import _summary

    report = RunReport(dry_run=dry_run)
    report.accepted.extend(candidates)
    return _summary(report)


def test_summary_shows_the_link_and_place_of_each_proposed_event():
    # A dry run is judged on exactly these two things, so a title and a date alone are useless.
    out = _summary_for(
        _accepted(
            source_url="https://velogearance.ru/tg26/",
            country="Russia",
            region="Ryazan Oblast",
            city="Skopin",
            venue="Troitskaya Grove",
            lat=53.801524,
            lng=39.549943,
        )
    )
    assert "link:  https://velogearance.ru/tg26/" in out
    assert "Russia / Ryazan Oblast / Skopin / Troitskaya Grove (53.801524, 39.549943)" in out


def test_summary_makes_a_missing_link_and_place_visible():
    out = _summary_for(_accepted())
    assert "link:  (none)" in out
    assert "(no place) (no coordinate)" in out


def test_summary_reports_a_place_without_a_coordinate():
    out = _summary_for(_accepted(country="Russia", city="Moscow"))
    assert "Russia / Moscow (no coordinate)" in out


def _candidates(prefix: str, count: int) -> list:
    return [Candidate(title=f"{prefix} {n}", date_start="2026-09-26", description="d") for n in range(count)]


def test_one_source_cannot_take_the_whole_run():
    """A calendar of the world's races never runs out; our own organizers do, once harvested.

    Without a per-source budget the deepest source takes every slot -- three runs in a row proposed
    nothing but foreign marathons while the cycling sources returned only events already on the site.
    """
    deep, shallow = _src("https://deep.example"), _src("https://shallow.example")
    report, created = _run(
        [deep, shallow],
        {deep.fetch_url: _candidates("Deep", 20), shallow.fetch_url: _candidates("Shallow", 3)},
        max_events=10,
        max_per_source=5,
    )
    titles = [c.title for c in report.accepted]
    assert sum(t.startswith("Deep") for t in titles) == 5
    assert sum(t.startswith("Shallow") for t in titles) == 3
    assert len(created) == 8


def test_a_source_that_hits_its_budget_is_named_in_the_report():
    deep = _src("https://deep.example")
    report, _ = _run([deep], {deep.fetch_url: _candidates("Deep", 9)}, max_per_source=5)
    assert report.source_capped == [deep.fetch_url]
    assert report.capped is False  # the run itself still has room; only this source is done


def test_no_per_source_budget_means_no_limit():
    deep = _src("https://deep.example")
    report, _ = _run([deep], {deep.fetch_url: _candidates("Deep", 9)}, max_per_source=0)
    assert len(report.accepted) == 9
    assert report.source_capped == []


def test_the_budget_counts_accepted_events_not_candidates_looked_at():
    """Duplicates and past events cost a source nothing -- otherwise a noisy source starves itself."""
    src = _src("https://mixed.example")
    stale = [Candidate(title=f"Old {n}", date_start="2020-01-01", description="d") for n in range(6)]
    report, _ = _run([src], {src.fetch_url: stale + _candidates("Good", 4)}, max_per_source=5)
    assert [c.title for c in report.accepted] == [f"Good {n}" for n in range(4)]


def test_every_source_reports_what_it_contributed():
    """Including the ones that gave nothing: "where did this run's events come from" is the
    question a log has to answer, and a source that quietly yields its whole budget and then runs
    dry is indistinguishable from one that was cut short unless the count is always there."""
    generous, empty = _src("https://generous.example"), _src("https://empty.example")
    report, _ = _run(
        [generous, empty],
        {generous.fetch_url: _candidates("Good", 3), empty.fetch_url: []},
        max_per_source=5,
    )
    assert report.proposed_by_source == {generous.fetch_url: 3, empty.fetch_url: 0}


def test_a_capped_source_reports_exactly_its_budget():
    deep = _src("https://deep.example")
    report, _ = _run([deep], {deep.fetch_url: _candidates("Deep", 9)}, max_per_source=4)
    assert report.proposed_by_source == {deep.fetch_url: 4}
