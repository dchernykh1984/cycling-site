import datetime
from dataclasses import replace

from agent.models import Candidate, KnownEvents, Source, Taxonomy
from agent.pipeline import normalize_key, parse_candidates, run_pipeline

TODAY = datetime.date(2026, 7, 1)


def _src(url="https://x.kz"):
    return Source("website", url, url)


def _run(sources, by_source, *, known=None, max_events=10, dry_run=False):
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
    assert report.skipped_sources
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
