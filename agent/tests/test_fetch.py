from urllib.error import HTTPError, URLError

import pytest

import agent.fetch as fetch
from agent.fetch import _fetch_urls, extract_links


def test_fetch_urls_adds_telegram_alias_fallbacks():
    assert _fetch_urls("https://t.me/s/roadcyclingkz") == [
        "https://t.me/s/roadcyclingkz",
        "https://telegram.dog/s/roadcyclingkz",
        "https://telegram.me/s/roadcyclingkz",
    ]


def test_fetch_urls_leaves_non_telegram_urls_untouched():
    assert _fetch_urls("https://redbikecup.ru/rbc/2026") == ["https://redbikecup.ru/rbc/2026"]


def test_extract_links_resolves_relative_against_base():
    html = '<a href="/rbc/2026/6">Event page</a> <a href="https://strava.com/routes/1">Track</a>'
    links = extract_links(html, "https://redbikecup.ru/rbc/2026")
    assert "https://redbikecup.ru/rbc/2026/6" in links  # relative resolved to absolute
    assert "https://strava.com/routes/1" in links


def test_extract_links_skips_non_http_and_dedups():
    html = (
        '<a href="#top">a</a><a href="mailto:x@y.z">m</a><a href="tel:+7700">t</a>'
        '<a href="javascript:void(0)">j</a><a href="https://a.kz/x">A</a><a href="https://a.kz/x">A2</a>'
    )
    assert extract_links(html, "https://a.kz") == ["https://a.kz/x"]


def test_extract_links_empty_without_anchors():
    assert extract_links("<p>no links here</p>", "https://a.kz") == []


def test_extract_links_respects_limit():
    html = "".join(f'<a href="https://a.kz/{i}">e</a>' for i in range(300))
    assert len(extract_links(html, "https://a.kz")) == fetch._MAX_LINKS  # default cap (60)
    # Aggregators pass the wider cap so many races on a calendar page are surfaced, not just the top.
    assert len(extract_links(html, "https://a.kz", limit=fetch._AGGREGATOR_MAX_LINKS)) == 200


def test_fetch_source_surfaces_more_links_for_aggregators(monkeypatch):
    from agent.models import Source

    html = "<body>" + "".join(f'<a href="https://a.kz/{i}">e</a>' for i in range(300)) + "</body>"
    monkeypatch.setattr(fetch, "_get_with_fallback", lambda url, *a, **k: html)
    aggregator = fetch.fetch_source(Source("aggregator", "ref", "https://cal.kz/"))
    organizer = fetch.fetch_source(Source("organizer", "ref", "https://cal.kz/"))
    assert aggregator.count("https://a.kz/") == fetch._AGGREGATOR_MAX_LINKS  # 200 for a calendar
    assert organizer.count("https://a.kz/") == fetch._MAX_LINKS  # 60 for a normal site


def test_fetch_source_keeps_more_text_for_aggregators(monkeypatch):
    from agent.models import Source

    html = "<body><p>" + ("x " * 20000) + "</p></body>"  # ~40k chars of text, no links
    monkeypatch.setattr(fetch, "_get_with_fallback", lambda url, *a, **k: html)
    aggregator = fetch.fetch_source(Source("aggregator", "ref", "https://cal.kz/"))
    organizer = fetch.fetch_source(Source("organizer", "ref", "https://cal.kz/"))
    assert len(aggregator) > fetch._MAX_CHARS  # a calendar keeps the wider text budget
    assert len(organizer) <= fetch._MAX_CHARS + 20  # a normal site stays tightly capped


def _no_sleep(monkeypatch):
    monkeypatch.setattr(fetch.time, "sleep", lambda _s: None)


def test_get_with_fallback_retries_telegram_until_an_alias_resolves(monkeypatch):
    _no_sleep(monkeypatch)
    calls = []

    def fake_get(url, timeout=20):
        calls.append(url)
        if len(calls) < 4:  # fail the whole first pass (t.me, telegram.dog, telegram.me)
            raise URLError("Name or service not known")
        return "posts"

    monkeypatch.setattr(fetch, "_get", fake_get)
    assert fetch._get_with_fallback("https://t.me/s/kztime") == "posts"
    assert len(calls) == 4  # retried past the first failed pass


def test_get_with_fallback_gives_up_after_the_retry_budget(monkeypatch):
    _no_sleep(monkeypatch)
    calls = []

    def fake_get(url, timeout=20):
        calls.append(url)
        raise URLError("dns")

    monkeypatch.setattr(fetch, "_get", fake_get)
    with pytest.raises(URLError):
        fetch._get_with_fallback("https://t.me/s/kztime")
    assert len(calls) == 9  # 3 alias hosts x 3 passes


def test_get_with_fallback_does_not_retry_a_website(monkeypatch):
    _no_sleep(monkeypatch)
    calls = []

    def fake_get(url, timeout=20):
        calls.append(url)
        raise URLError("down")

    monkeypatch.setattr(fetch, "_get", fake_get)
    with pytest.raises(URLError):
        fetch._get_with_fallback("https://redbikecup.ru/x")
    assert calls == ["https://redbikecup.ru/x"]  # a single attempt, no retry


def test_get_with_fallback_does_not_retry_http_errors(monkeypatch):
    _no_sleep(monkeypatch)
    calls = []

    def fake_get(url, timeout=20):
        calls.append(url)
        raise HTTPError(url, 404, "Not Found", None, None)

    monkeypatch.setattr(fetch, "_get", fake_get)
    with pytest.raises(HTTPError):
        fetch._get_with_fallback("https://t.me/s/kztime")
    assert len(calls) == 1  # 404 is a real answer -> no fallback, no retry
