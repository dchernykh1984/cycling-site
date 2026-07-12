import datetime

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
