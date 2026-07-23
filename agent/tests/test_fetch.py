import socket
import urllib.request
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


def test_fetch_source_line_structures_aggregators_only(monkeypatch):
    from agent.models import Source

    html = "<table><tr><td>August</td></tr><tr><td>8</td><td>XCO Race</td></tr></table>"
    monkeypatch.setattr(fetch, "_get_with_fallback", lambda url, *a, **k: html)
    aggregator = fetch.fetch_source(Source("aggregator", "r", "https://cal.kz/")).split("Links on the page:")[0]
    organizer = fetch.fetch_source(Source("organizer", "r", "https://cal.kz/")).split("Links on the page:")[0]
    assert "\n" in aggregator  # a calendar keeps each cell/row on its own line
    assert "\n" not in organizer  # a normal page stays space-joined


def test_sniff_charset_reads_meta_when_header_missing():
    assert fetch._sniff_charset(b'<meta charset="windows-1251">') == "windows-1251"
    assert fetch._sniff_charset(b"\xef\xbb\xbf<html>") == "utf-8"  # a UTF-8 BOM wins
    assert fetch._sniff_charset(b"<html>no declared charset here</html>") is None


def test_get_decodes_via_meta_charset_when_header_missing(monkeypatch):
    word = "\u0413\u043e\u043d\u043a\u0430"  # a Cyrillic word, escaped to keep the source ASCII
    body = ('<meta charset="windows-1251"><p>' + word + "</p>").encode("cp1251")

    class _Headers:
        def get_content_charset(self):
            return None  # server sent no charset -> _get must sniff the <meta>

    class _Resp:
        headers = _Headers()

        def read(self):
            return body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(fetch.urllib.request, "urlopen", lambda *a, **k: _Resp())
    assert word in fetch._get("https://bike-events.ru/")  # windows-1251 bytes decoded correctly


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
    assert len(calls) == 3 * fetch._FETCH_RETRIES  # 3 alias hosts x N passes


def test_get_with_fallback_retries_a_website_on_timeout(monkeypatch):
    _no_sleep(monkeypatch)
    calls = []

    def fake_get(url, timeout=20):
        calls.append(url)
        raise TimeoutError("timed out")

    monkeypatch.setattr(fetch, "_get", fake_get)
    with pytest.raises(TimeoutError):
        fetch._get_with_fallback("https://bitza-sport.ru/")
    assert calls == ["https://bitza-sport.ru/"] * fetch._FETCH_RETRIES  # one host, retried N passes


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


def test_get_with_fallback_retries_a_transient_5xx(monkeypatch):
    _no_sleep(monkeypatch)
    calls = []

    def fake_get(url, timeout=20):
        calls.append(url)
        raise HTTPError(url, 503, "Service Unavailable", None, None)

    monkeypatch.setattr(fetch, "_get", fake_get)
    with pytest.raises(HTTPError):
        fetch._get_with_fallback("https://bitza-sport.ru/")
    assert len(calls) == fetch._FETCH_RETRIES  # 503 is transient -> retried, not dropped


def _addrinfo(ip, port):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]


def test_fetch_track_over_https_reaches_the_guarded_connection(monkeypatch):
    """Regression: the HTTPS handler must not touch a missing _check_hostname attr on Python 3.12+.

    Before the fix, opening any https track raised AttributeError inside https_open -- swallowed by
    start_coordinate, so no coordinate was ever read. Here the fetch must get all the way to the
    guarded connection (our marker), proving handler setup no longer raises.
    """
    marker = RuntimeError("reached the guarded connection")

    def boom(*args, **kwargs):
        raise marker

    monkeypatch.setattr(fetch, "_guarded_create_connection", boom)
    with pytest.raises(RuntimeError, match="reached the guarded connection"):
        fetch.fetch_track("https://93.184.216.34/route.gpx")


def test_guarded_create_connection_refuses_a_rebound_private_ip(monkeypatch):
    """The track fetch must connect to the very IPs it validated -- a resolved private one is refused."""
    monkeypatch.setattr(fetch.socket, "getaddrinfo", lambda *a, **k: _addrinfo("169.254.169.254", 80))

    def no_socket(*a, **k):
        raise AssertionError("must not open a socket to a blocked address")

    monkeypatch.setattr(fetch.socket, "socket", no_socket)
    with pytest.raises(OSError, match="non-public"):
        fetch._guarded_create_connection(("rebind.evil.test", 80))


def test_track_opener_ignores_a_configured_proxy(monkeypatch):
    """A configured HTTP(S)_PROXY must not route the track fetch through an unchecked proxy.

    Built with the same env set, a plain build_opener would register a ProxyHandler carrying the
    env's proxies; the track opener must have no active proxy handler so the IP guard stays the only
    arbiter of where the socket connects.
    """
    monkeypatch.setenv("HTTP_PROXY", "http://192.168.0.1:3128")
    monkeypatch.setenv("HTTPS_PROXY", "http://192.168.0.1:3128")
    active = [
        h for h in fetch._build_track_opener().handlers if isinstance(h, urllib.request.ProxyHandler) and h.proxies
    ]
    assert not active  # no proxy applied even though the environment sets one


def test_guarded_create_connection_dials_the_validated_ip_not_the_hostname(monkeypatch):
    """It connects to the address it resolved and checked, never re-resolving the name."""
    monkeypatch.setattr(fetch.socket, "getaddrinfo", lambda *a, **k: _addrinfo("93.184.216.34", 443))
    dialed = {}

    class _Sock:
        def settimeout(self, t):
            pass

        def connect(self, sockaddr):
            dialed["to"] = sockaddr

        def close(self):
            pass

    monkeypatch.setattr(fetch.socket, "socket", lambda *a, **k: _Sock())
    fetch._guarded_create_connection(("example.test", 443))
    assert dialed["to"] == ("93.184.216.34", 443)
