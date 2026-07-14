"""Fetch a source's recent text (network + HTML parsing). Coverage-omitted I/O adapter.

The text handed to the LLM also lists the page's real hyperlink URLs, because ``get_text`` drops
``<a href>`` targets -- so without this the model never sees the actual links and tends to invent
them or miss the specific event page. ``extract_links`` (the pure part) has its own unit tests.
"""

from __future__ import annotations

import urllib.request
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from agent.models import Source

_UA = "Mozilla/5.0 (compatible; UniversalBicycleTeam-EventsAgent/1.0)"
_MAX_CHARS = 12000  # keep LLM prompts bounded
_MAX_LINKS = 60
_SKIP_PREFIXES = ("#", "javascript:", "mailto:", "tel:")


def _get(url: str, timeout: int = 20) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _absolute_links(anchors, base_url: str) -> list[str]:
    """Deduped absolute http(s) URLs from ``<a href>`` anchors, resolved against ``base_url``."""
    seen: list[str] = []
    for anchor in anchors:
        href = (anchor.get("href") or "").strip()
        if not href or href.startswith(_SKIP_PREFIXES):
            continue
        url = urljoin(base_url, href)
        if urlsplit(url).scheme in ("http", "https") and url not in seen:
            seen.append(url)
            if len(seen) >= _MAX_LINKS:
                break
    return seen


def extract_links(html: str, base_url: str) -> list[str]:
    """Absolute http(s) links found in ``html`` (pure; used by the fetchers, unit-tested)."""
    return _absolute_links(BeautifulSoup(html, "html.parser").find_all("a", href=True), base_url)


def _with_links(text: str, anchors, base_url: str) -> str:
    links = _absolute_links(anchors, base_url)
    body = text[:_MAX_CHARS]
    if links:
        body += "\n\nLinks on the page:\n" + "\n".join(links)
    return body


def fetch_url(url: str, timeout: int = 20) -> str:
    """Readable text of an arbitrary web page (plus its links), for enriching an event."""
    soup = BeautifulSoup(_get(url, timeout), "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return _with_links(soup.get_text(" ", strip=True), soup.find_all("a", href=True), url)


def fetch_source(source: Source) -> str:
    """Return readable text for a website or public Telegram channel (via the t.me/s/ preview)."""
    if not source.fetch_url:
        raise ValueError("source is not fetchable")
    soup = BeautifulSoup(_get(source.fetch_url), "html.parser")
    if source.kind == "tg_public":
        posts = soup.select(".tgme_widget_message_text")
        text = "\n\n".join(post.get_text(" ", strip=True) for post in posts)
        anchors = [anchor for post in posts for anchor in post.find_all("a", href=True)]
    else:
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
        anchors = soup.find_all("a", href=True)
    return _with_links(text, anchors, source.fetch_url)
