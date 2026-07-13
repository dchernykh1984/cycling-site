from dataclasses import replace

from agent.enrich import merge_candidate, should_enrich
from agent.models import Candidate


def _cand(**kw):
    return replace(Candidate(title="Race", date_start="2026-08-01"), **kw)


def test_should_enrich_true_for_a_specific_page():
    assert should_enrich(_cand(source_url="https://athletex.kz/competitions/aqb6")) is True


def test_should_enrich_false_for_homepage_or_bad_url():
    assert should_enrich(_cand(source_url="https://athletex.kz/")) is False  # bare homepage
    assert should_enrich(_cand(source_url="https://athletex.kz")) is False  # no path
    assert should_enrich(_cand(source_url="")) is False
    assert should_enrich(_cand(source_url="ftp://host/x")) is False  # not http(s)
    assert should_enrich(_cand(source_url="not a url")) is False


def test_merge_prefers_refined_nonempty_and_keeps_base_otherwise():
    base = _cand(source_url="https://x.kz/e/1", description="short", url_route="", title_en="Race EN")
    refined = _cand(
        source_url="https://echo/ignored",
        description="<p>full</p>",
        url_route="https://strava.com/routes/1",
        title_en="",  # empty -> base's value is kept
    )
    merged = merge_candidate(base, refined)
    assert merged.description == "<p>full</p>"  # refined wins
    assert merged.url_route == "https://strava.com/routes/1"  # refined fills an empty base field
    assert merged.title_en == "Race EN"  # base kept where refined is empty
    assert merged.source_url == "https://x.kz/e/1"  # the announcement page is preserved


def test_merge_keeps_base_when_refinement_is_empty():
    base = _cand(source_url="https://x.kz/e/1", description="keep me", city="Almaty")
    refined = Candidate(title="", date_start="")  # nothing useful came back
    merged = merge_candidate(base, refined)
    assert merged.title == "Race"
    assert merged.description == "keep me"
    assert merged.city == "Almaty"
