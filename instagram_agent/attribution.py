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
_EMPTY_TAGS = re.compile(r"<(p|li)>\s*</\1>", re.IGNORECASE)
_SPACES = re.compile(r"[ \t]{2,}")

# The credit line, per locale. Russian is the wording the maintainer asked for; the other two say
# the same thing. None of them names a platform.
_CREDIT = {
    "ru": "".join(chr(c) for c in (0x418, 0x441, 0x442, 0x43E, 0x447, 0x43D, 0x438, 0x43A))  # Istochnik
    + " "
    + "".join(chr(c) for c in (0x43E, 0x431, 0x44A, 0x44F, 0x432, 0x43B, 0x435, 0x43D, 0x438, 0x44F)),  # obyavleniya
    "kk": "".join(chr(c) for c in (0x425, 0x430, 0x431, 0x430, 0x440, 0x43B, 0x430, 0x43D, 0x434, 0x44B, 0x440, 0x443))
    + " "
    + "".join(chr(c) for c in (0x43A, 0x4E9, 0x437, 0x456)),  # "Khabarlandyru kozi"
    "en": "Announcement source",
}


def _strip_platform(text: str) -> str:
    """Remove links and any naming of the platform, leaving the rest of the text readable."""
    without_links = _HTML_LINK.sub(r"\1", text or "")
    without_links = _URL.sub("", without_links)
    scrubbed = _PLATFORM.sub("", without_links)
    scrubbed = _EMPTY_TAGS.sub("", scrubbed)
    return _SPACES.sub(" ", scrubbed).strip()


def _with_credit(text: str, handle: str, locale: str) -> str:
    """The description with the credit line appended, as its own paragraph."""
    body = _strip_platform(text)
    credit = f"<p>{_CREDIT[locale]}: {handle}</p>"
    return f"{body}\n{credit}" if body else credit


def credit_account(candidate: Candidate, account: Account) -> Candidate:
    """The candidate as it may be published: credited to the account, with nothing else attached."""
    handle = f"@{account.username}"
    return replace(
        candidate,
        description=_with_credit(candidate.description, handle, "ru"),
        description_kk=_with_credit(candidate.description_kk, handle, "kk"),
        description_en=_with_credit(candidate.description_en, handle, "en"),
        # The announcement, route and registration fields are shown on the event page and would each
        # carry a link to the post. There is no other link to put there, so they stay empty.
        source_url="",
        url_route="",
        url_registration="",
        title=_strip_platform(candidate.title),
        title_kk=_strip_platform(candidate.title_kk),
        title_en=_strip_platform(candidate.title_en),
    )
