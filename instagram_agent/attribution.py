"""Credit a proposed event to the account it came from, and to nothing else (no I/O, unit-tested).

A published event says where it was announced only as the account's own name -- "Istochnik
obyavleniya: @ubtalmaty", in Russian -- and never names the platform the account is on, nor links a
post on it.
The reason is not editorial: the site's maintainer is a Russian citizen, and the platform these
accounts live on is designated extremist in Russia. Naming it on a public page he runs is a legal
risk he should not have to take to publish a Saturday ride.

So this is enforced here rather than asked of the model. A prompt can be forgotten mid-reply; a
function cannot. Everything a run proposes passes through :func:`credit_account`, which strips any
mention that slipped in, drops the links, and appends the one line that is allowed.
"""

from __future__ import annotations

import re
from dataclasses import replace

from agent.credit import with_credit
from agent.models import Candidate
from instagram_agent.accounts import Account

# The platform's name in the spellings a caption or a model reply might use, plus the domains its
# links carry. Matched case-insensitively and, for the Cyrillic forms, by code point so this file
# stays ASCII-only like the rest of the source.
_INSTA_LATIN = "instagram|insta|ig\\.me"
_INSTA_CYRILLIC = "".join(chr(c) for c in (0x438, 0x43D, 0x441, 0x442, 0x430))  # "insta" in Cyrillic
_PLATFORM = re.compile(rf"({_INSTA_LATIN}|{_INSTA_CYRILLIC}\w*)", re.IGNORECASE)
_URL = re.compile(r"https?://[^\s<]+|\bwww\.[^\s<]+", re.IGNORECASE)
_HTML_LINK = re.compile(r"<a\b[^>]*>(.*?)</a>", re.IGNORECASE | re.DOTALL)
# Anything that would make a reader's browser fetch a file from the platform. No image is ever
# collected from a post -- the reader does not even read the media fields -- but a model can write
# an <img> into a description, and a hotlinked image is the platform on the page as surely as its
# name is. Paired tags go with their contents; void ones go on their own.
_MEDIA_BLOCK = re.compile(r"<(video|picture|iframe|object|figure|audio)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_MEDIA_TAG = re.compile(r"</?(img|source|embed|track|svg|canvas|video|iframe|picture)\b[^>]*/?>", re.IGNORECASE)
_EMPTY_TAGS = re.compile(r"<(p|li)>\s*</\1>", re.IGNORECASE)
_SPACES = re.compile(r"[ \t]{2,}")


def _strip_platform(text: str) -> str:
    """Remove links, embedded media and any naming of the platform; keep the text readable."""
    without_media = _MEDIA_BLOCK.sub("", text or "")
    without_media = _MEDIA_TAG.sub("", without_media)
    without_links = _HTML_LINK.sub(r"\1", without_media)
    without_links = _URL.sub("", without_links)
    scrubbed = _PLATFORM.sub("", without_links)
    scrubbed = _EMPTY_TAGS.sub("", scrubbed)
    return _SPACES.sub(" ", scrubbed).strip()


def credit_account(candidate: Candidate, account: Account) -> Candidate:
    """The candidate as it may be published: credited to the account, with nothing else attached."""
    handle = f"@{account.username}"
    return replace(
        candidate,
        description=with_credit(_strip_platform(candidate.description), handle, "ru"),
        description_kk=with_credit(_strip_platform(candidate.description_kk), handle, "kk"),
        description_en=with_credit(_strip_platform(candidate.description_en), handle, "en"),
        # The announcement, route and registration fields are shown on the event page and would each
        # carry a link to the post. There is no other link to put there, so they stay empty.
        source_url="",
        url_route="",
        url_registration="",
        title=_strip_platform(candidate.title),
        title_kk=_strip_platform(candidate.title_kk),
        title_en=_strip_platform(candidate.title_en),
    )
