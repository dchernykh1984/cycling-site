"""Fetch a source's recent text (network + HTML parsing). Coverage-omitted I/O adapter."""

from __future__ import annotations

import urllib.request

from bs4 import BeautifulSoup

from agent.models import Source

_UA = "Mozilla/5.0 (compatible; UniversalBicycleTeam-EventsAgent/1.0)"
_MAX_CHARS = 12000  # keep LLM prompts bounded


def _get(url: str, timeout: int = 20) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def fetch_url(url: str, timeout: int = 20) -> str:
    """Readable text of an arbitrary web page, for enriching an event from its own page."""
    soup = BeautifulSoup(_get(url, timeout), "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(" ", strip=True)[:_MAX_CHARS]


def fetch_source(source: Source) -> str:
    """Return readable text for a website or public Telegram channel (via the t.me/s/ preview)."""
    if not source.fetch_url:
        raise ValueError("source is not fetchable")
    soup = BeautifulSoup(_get(source.fetch_url), "html.parser")
    if source.kind == "tg_public":
        posts = soup.select(".tgme_widget_message_text")
        text = "\n\n".join(post.get_text(" ", strip=True) for post in posts)
    else:
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
    return text[:_MAX_CHARS]
