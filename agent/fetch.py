"""Fetch a source's recent text (network + HTML parsing). Coverage-omitted I/O adapter.

The text handed to the LLM also lists the page's real hyperlink URLs, because ``get_text`` drops
``<a href>`` targets -- so without this the model never sees the actual links and tends to invent
them or miss the specific event page. ``extract_links`` (the pure part) has its own unit tests.
"""

from __future__ import annotations

import re
import time
import urllib.request
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from agent.models import Source

_UA = "Mozilla/5.0 (compatible; UniversalBicycleTeam-EventsAgent/1.0)"
_MAX_CHARS = 12000  # keep LLM prompts bounded
_MAX_LINKS = 60
# Aggregator/calendar pages list many races, each linking to its own page; surface far more of those
# links -- and proportionally more page text -- so the model sees the name/date next to each of the
# nearest upcoming events instead of only the top of the page.
_AGGREGATOR_MAX_LINKS = 200
_AGGREGATOR_MAX_CHARS = 30000
_SKIP_PREFIXES = ("#", "javascript:", "mailto:", "tel:")
# Telegram serves the same content on these alias domains; t.me has gone NXDOMAIN, so fall back.
_TG_HOSTS = ("t.me", "telegram.dog", "telegram.me")
_FETCH_RETRIES = 4  # retry a timed-out / unreachable source a few times (it runs at night, unhurried)
_RETRY_BACKOFF = 10.0  # seconds between retry passes


# When the HTTP response omits a charset, fall back to the one the HTML declares (some RU calendars
# serve windows-1251 and announce it only in a <meta> tag) rather than assuming UTF-8 and garbling.
_META_CHARSET = re.compile(rb'charset=["\']?\s*([A-Za-z0-9_-]+)', re.IGNORECASE)


def _sniff_charset(raw: bytes) -> str | None:
    """The charset from the page's BOM or <meta>, used only when the HTTP header omits one."""
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8"
    match = _META_CHARSET.search(raw[:2048])
    return match.group(1).decode("ascii", "ignore") if match else None


def _get(url: str, timeout: int = 20) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        charset = response.headers.get_content_charset()
    try:
        return raw.decode(charset or _sniff_charset(raw) or "utf-8", errors="replace")
    except LookupError:  # an unknown / misspelled charset name in the header or meta
        return raw.decode("utf-8", errors="replace")


def _fetch_urls(url: str) -> list[str]:
    """The URL, plus Telegram alias fallbacks when it points at a t.me/telegram.dog/telegram.me host."""
    parts = urlsplit(url)
    if parts.netloc not in _TG_HOSTS:
        return [url]
    return [urlunsplit(parts._replace(netloc=host)) for host in _TG_HOSTS]


def _get_with_fallback(url: str, timeout: int = 20) -> str:
    """Fetch ``url``, retrying on a timeout / connection failure (but never on an HTTP error).

    A timed-out or unreachable source is retried ``_FETCH_RETRIES`` times with a backoff: the
    pipeline runs unattended at night, so a transient network hiccup should not silently drop a whole
    source. For Telegram, each pass also cycles the alias hosts (t.me is intermittently NXDOMAIN on
    the runner). An HTTP error (e.g. 404) means the server answered, so it is raised without retrying.
    """
    urls = _fetch_urls(url)
    passes = _FETCH_RETRIES
    last_exc: Exception | None = None
    for attempt in range(passes):
        for candidate in urls:
            try:
                return _get(candidate, timeout)
            except HTTPError as exc:
                if exc.code not in (502, 503, 504):
                    raise  # a definitive answer (e.g. 404 / 403) -- not worth retrying
                last_exc = exc  # transient gateway / unavailable -- retry like a timeout
            except (URLError, TimeoutError) as exc:
                last_exc = exc  # DNS / connection failure -- try the next alias host
        if attempt + 1 < passes:
            time.sleep(_RETRY_BACKOFF)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"no URL to fetch for {url}")  # unreachable: _fetch_urls always yields >= 1


def _absolute_links(anchors, base_url: str, limit: int = _MAX_LINKS) -> list[str]:
    """Deduped absolute http(s) URLs from ``<a href>`` anchors, resolved against ``base_url``."""
    seen: list[str] = []
    for anchor in anchors:
        href = (anchor.get("href") or "").strip()
        if not href or href.startswith(_SKIP_PREFIXES):
            continue
        url = urljoin(base_url, href)
        if urlsplit(url).scheme in ("http", "https") and url not in seen:
            seen.append(url)
            if len(seen) >= limit:
                break
    return seen


def extract_links(html: str, base_url: str, limit: int = _MAX_LINKS) -> list[str]:
    """Absolute http(s) links found in ``html`` (pure; used by the fetchers, unit-tested)."""
    return _absolute_links(BeautifulSoup(html, "html.parser").find_all("a", href=True), base_url, limit)


def _with_links(text: str, anchors, base_url: str, limit: int = _MAX_LINKS, max_chars: int = _MAX_CHARS) -> str:
    links = _absolute_links(anchors, base_url, limit)
    body = text[:max_chars]
    if links:
        body += "\n\nLinks on the page:\n" + "\n".join(links)
    return body


def fetch_url(url: str, timeout: int = 20) -> str:
    """Readable text of an arbitrary web page (plus its links), for enriching an event."""
    soup = BeautifulSoup(_get_with_fallback(url, timeout), "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return _with_links(soup.get_text(" ", strip=True), soup.find_all("a", href=True), url)


def fetch_source(source: Source) -> str:
    """Return readable text for a website or public Telegram channel (via the t.me/s/ preview)."""
    if not source.fetch_url:
        raise ValueError("source is not fetchable")
    soup = BeautifulSoup(_get_with_fallback(source.fetch_url), "html.parser")
    if source.kind == "tg_public":
        posts = soup.select(".tgme_widget_message_text")
        text = "\n\n".join(post.get_text(" ", strip=True) for post in posts)
        anchors = [anchor for post in posts for anchor in post.find_all("a", href=True)]
    else:
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        # Aggregators are dense race lists/tables: keep each row on its own line so the model can
        # enumerate them one by one; ordinary pages read better as flowing space-joined prose.
        separator = "\n" if source.kind == "aggregator" else " "
        text = soup.get_text(separator, strip=True)
        anchors = soup.find_all("a", href=True)
    if source.kind == "aggregator":
        limit, max_chars = _AGGREGATOR_MAX_LINKS, _AGGREGATOR_MAX_CHARS
    else:
        limit, max_chars = _MAX_LINKS, _MAX_CHARS
    return _with_links(text, anchors, source.fetch_url, limit, max_chars)
