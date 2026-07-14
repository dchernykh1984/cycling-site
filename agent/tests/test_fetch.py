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
