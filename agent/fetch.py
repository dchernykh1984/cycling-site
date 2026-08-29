"""Fetch a source's recent text (network + HTML parsing). Coverage-omitted I/O adapter.

The text handed to the LLM also lists the page's real hyperlinks -- each as the name it is shown
under and its URL -- because ``get_text`` drops ``<a href>`` targets, so without this the model
never sees the actual links and tends to invent them or miss the specific event page. The name
matters as much as the URL: a calendar's links are indistinguishable without it. The pure parts
(``extract_links`` and the collector behind it) have their own unit tests.
"""

from __future__ import annotations

import http.client
import ipaddress
import re
import socket
import time
import urllib.request
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from agent.geo import is_blocked_ip
from agent.links import LINKS_MARKER
from agent.models import Source

_UA = "Mozilla/5.0 (compatible; UniversalBicycleTeam-EventsAgent/1.0)"
_MAX_CHARS = 12000  # keep LLM prompts bounded
_MAX_LINKS = 60
_MAX_LINK_LABEL = 80  # anchor text is a race name, not prose -- enough to identify it, no more
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


def extract_links(html: str, base_url: str, limit: int = _MAX_LINKS) -> list[str]:
    """Absolute http(s) links found in ``html`` (pure; unit-tested).

    The URL-only view of :func:`_named_links`, so the collecting rules -- resolve against the base,
    http(s) only, deduped, capped -- live in one place and cannot drift between the two callers.
    """
    anchors = BeautifulSoup(html, "html.parser").find_all("a", href=True)
    return [url for _, url in _named_links(anchors, base_url, limit)]


def _labelled_links(anchors, base_url: str, limit: int = _MAX_LINKS) -> list[str]:
    """``"<anchor text> - <url>"`` per link, so a race can be matched to its own page.

    A calendar lists every race as a link whose text is the race's name, but a bare list of URLs
    (``.../race.php?race=2608``) says nothing about which race each one belongs to -- the model
    cannot pick an event's own page from it and leaves the link empty. Carrying the anchor text is
    what makes that choice possible. Text is squeezed onto one line and capped so a long or
    image-only anchor cannot crowd out the list.
    """
    return [f"{name} - {url}" if name else url for name, url in _named_links(anchors, base_url, limit)]


def _named_links(anchors, base_url: str, limit: int = _MAX_LINKS) -> list[tuple[str, str]]:
    """``(name, url)`` per deduped http(s) link, in page order, capped at ``limit``.

    The name is empty when nothing on the page names the link.
    """
    order: list[str] = []
    names: dict[str, str] = {}
    for anchor in anchors:
        href = (anchor.get("href") or "").strip()
        if not href or href.startswith(_SKIP_PREFIXES):
            continue
        url = urljoin(base_url, href)
        if urlsplit(url).scheme not in ("http", "https"):
            continue
        if url not in names:
            if len(order) >= limit:
                continue
            order.append(url)
            names[url] = ""
        # A calendar routinely links the same race twice -- once around its logo (no text) and once
        # around its name -- so keep looking until a named one turns up rather than taking the
        # first. The image's title/alt carries the name too, and serves when only the logo links.
        if not names[url]:
            names[url] = _anchor_label(anchor)
    return [(names[url], url) for url in order]


def _anchor_label(anchor) -> str:
    """The race name an anchor stands for: its own text, else its title, else its image's."""
    for raw in (anchor.get_text(" ", strip=True), anchor.get("title"), *_image_labels(anchor)):
        label = " ".join((raw or "").split())
        if label:
            return label[:_MAX_LINK_LABEL]
    return ""


def _image_labels(anchor):
    for image in anchor.find_all("img"):
        yield image.get("title")
        yield image.get("alt")


def _with_links(text: str, anchors, base_url: str, limit: int = _MAX_LINKS, max_chars: int = _MAX_CHARS) -> str:
    links = _labelled_links(anchors, base_url, limit)
    body = text[:max_chars]
    if links:
        body += LINKS_MARKER + "\n".join(links)
    return body


_TRACK_MAX_BYTES = 20 * 1024 * 1024  # a GPS track is a few MB; cap the read so a hostile URL can't
# stream unbounded data into memory.


class _NoUnsafeRedirect(urllib.request.HTTPRedirectHandler):
    """Reject a redirect to a non-http(s) scheme before following it.

    A public decoy can answer 302 -> file:///etc/passwd or ftp://..., and the default opener carries
    FileHandler/FTPHandler that would serve it. The per-connection guard below already refuses any
    hop that resolves to a private address, so this only has to keep the scheme http(s).
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        from agent.geo import is_fetchable_track_url

        if not is_fetchable_track_url(newurl):
            raise URLError(f"unsafe redirect to {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _guarded_create_connection(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None):
    """Resolve ``address`` once, refuse it if any resolved IP is not public, then connect to it.

    The URL gate resolves the host to decide whether to fetch, but the socket layer would resolve it
    a *second* time to connect -- a host whose DNS returns a public address on the first lookup and a
    private one on the second (TTL 0) slips a private target past the gate. Validating the very IPs
    this connection then dials, in one resolution, closes that rebinding window; because every
    redirect hop opens a fresh connection, each hop is guarded too.
    """
    host, port = address
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    for *_, sockaddr in infos:
        if is_blocked_ip(ipaddress.ip_address(sockaddr[0])):
            raise OSError(f"refusing to connect to non-public address {sockaddr[0]}")
    last: OSError | None = None
    for family, socktype, proto, _canon, sockaddr in infos:
        sock = None
        try:
            sock = socket.socket(family, socktype, proto)
            if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
                sock.settimeout(timeout)
            if source_address:
                sock.bind(source_address)
            sock.connect(sockaddr)  # a literal from getaddrinfo -- no second DNS lookup
            return sock
        except OSError as exc:
            last = exc
            if sock is not None:
                sock.close()
    raise last if last is not None else OSError(f"could not resolve {host}")


class _GuardedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _guarded_create_connection


class _GuardedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _guarded_create_connection


class _GuardedHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_GuardedHTTPConnection, req)


class _GuardedHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        # Mirror the stdlib HTTPSHandler.https_open exactly (it passes only ``context``): on
        # Python 3.12+ HTTPSHandler no longer keeps a ``_check_hostname`` attribute, so referencing
        # it raised AttributeError on every HTTPS fetch -- swallowed by start_coordinate, which is
        # why no track was ever read. check_hostname lives on the SSL context already.
        return self.do_open(_GuardedHTTPSConnection, req, context=self._context)


def _build_track_opener() -> urllib.request.OpenerDirector:
    """An opener that connects directly through the guarded handlers, never through a proxy.

    The empty ``ProxyHandler({})`` pins it to direct connections: it makes build_opener drop its
    default proxy handler, so with HTTP(S)_PROXY set the socket would otherwise dial the proxy --
    whose IP is the only one ``_guarded_create_connection`` then sees, letting the real (possibly
    internal) target go unchecked. The agent fetches public track files directly, so this costs
    nothing. (An empty ProxyHandler registers no ``*_open`` method, so no proxy handler remains.)
    """
    return urllib.request.build_opener(
        _NoUnsafeRedirect(),
        urllib.request.ProxyHandler({}),
        _GuardedHTTPHandler(),
        _GuardedHTTPSHandler(),
    )


_TRACK_OPENER = _build_track_opener()


def fetch_track(url: str, timeout: int = 20) -> str:
    """Raw text of a linked GPS-track file (GPX/KML) -- no HTML stripping, for coordinate parsing.

    Reads at most ``_TRACK_MAX_BYTES``: the start point is near the top of the file, and the cap
    stops a URL that resolves to something huge from exhausting memory. Redirects are followed only
    to hosts that pass the same public-IP check as the original URL.
    """
    request = urllib.request.Request(url, headers={"User-Agent": _UA})
    with _TRACK_OPENER.open(request, timeout=timeout) as response:
        raw = response.read(_TRACK_MAX_BYTES)
        charset = response.headers.get_content_charset()
    try:
        return raw.decode(charset or _sniff_charset(raw) or "utf-8", errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def fetch_url(url: str, timeout: int = 20) -> str:
    """Readable text of an arbitrary web page (plus its links), for enriching an event."""
    soup = BeautifulSoup(_get_with_fallback(url, timeout), "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return _with_links(soup.get_text(" ", strip=True), soup.find_all("a", href=True), url)


def telegram_posts(soup) -> list[str]:
    """Each post of a t.me/s/<channel> feed, headed by its own address (pure, unit-tested).

    The model is told to link the specific post an event was announced in, and until now it had no
    way to: the feed was flattened into text and the one thing that identifies a post -- the
    permalink Telegram puts on its date -- was thrown away with the rest of the markup. Events came
    out with no link at all, or with the channel's whole feed standing in for an announcement.

    A post whose address Telegram did not render is still handed over, without a header: its text
    may still be the announcement, and losing the event would cost more than losing the link.
    """
    posts = []
    for message in soup.select(".tgme_widget_message"):
        body = message.select_one(".tgme_widget_message_text")
        if body is None:
            continue
        text = body.get_text(" ", strip=True)
        posts.append(f"--- post {_post_url(message)}\n{text}" if _post_url(message) else text)
    return posts


def _post_url(message) -> str:
    """The address of one post: the id Telegram writes on the message, else its date's link."""
    ref = (message.get("data-post") or "").strip("/")
    if ref:
        return f"https://t.me/{ref}"
    date_link = message.select_one("a.tgme_widget_message_date")
    return (date_link.get("href") or "").strip() if date_link else ""


def fetch_source(source: Source) -> str:
    """Return readable text for a website or public Telegram channel (via the t.me/s/ preview)."""
    if not source.fetch_url:
        raise ValueError("source is not fetchable")
    soup = BeautifulSoup(_get_with_fallback(source.fetch_url), "html.parser")
    if source.kind == "tg_public":
        text = "\n\n".join(telegram_posts(soup))
        anchors = [
            anchor for body in soup.select(".tgme_widget_message_text") for anchor in body.find_all("a", href=True)
        ]
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
