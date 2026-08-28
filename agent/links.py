"""Making a link from an announcement fit the column it is going to be stored in.

An announcement carries the link whoever wrote it had in their clipboard, and that is usually a link
they copied out of a social network: the address of a Google form, plus a click-id the network glued
on to follow the reader around. The one that broke a nightly run twice ran to 294 characters against
a varchar(200) column, of which 194 were a Facebook ``fbclid`` -- the address itself was 99.

Those parameters mean nothing to whoever opens the link: they identify the click, not the page. So
they come off, which both shortens the link and stops the site republishing someone's tracking id.

Nothing here talks to the network, and nothing here rewrites the part of a URL that decides where it
goes -- only the query is touched, and only the parameters named below.
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit, urlunsplit

# What the site's URL columns hold (Django's URLField default). The agent talks to the site over
# HTTP and has no models to read it off, so it is written out here; the API answers an over-long
# value with a 422 naming its own limit, which is what would show up if these ever diverged.
MAX_URL_LENGTH = 200

# Parameters that identify the click rather than the page. Prefix entries cover the families that
# generate a name per campaign (utm_source, utm_content, ...) rather than one fixed key.
_TRACKING_PREFIXES = ("utm_",)
_TRACKING_KEYS = frozenset(
    {
        "fbclid",  # Facebook / Instagram
        "igshid",  # Instagram
        "igsh",
        "gclid",  # Google Ads
        "gbraid",
        "wbraid",
        "dclid",  # DoubleClick
        "msclkid",  # Microsoft Ads
        "yclid",  # Yandex Direct
        "ysclid",  # Yandex
        "_openstat",
        "twclid",  # X / Twitter
        "ttclid",  # TikTok
        "li_fat_id",  # LinkedIn
        "mc_cid",  # Mailchimp
        "mc_eid",
        "ref_src",  # Twitter share widgets
        "ref_url",
        "si",  # YouTube / Spotify share links
        "feature",  # youtu.be share links
        "share_id",
        "rdt_cid",  # Reddit
        "vero_id",
        "_hsenc",  # HubSpot
        "_hsmi",
        "hsCtaTracking",
        "oly_anon_id",
        "oly_enc_id",
        "spm",  # Alibaba family
        "scm",
    }
)


def is_tracking(key: str) -> bool:
    """Whether a query parameter follows the reader rather than choosing the page."""
    lowered = key.lower()
    return lowered in _TRACKING_KEYS or lowered.startswith(_TRACKING_PREFIXES)


def strip_tracking(url: str) -> str:
    """The same link without the parameters that only identify whoever clicked it.

    Anything that is not a recognised tracker is kept, exactly as it was written and in the order it
    was written. A query is how a page is chosen as often as it is how a click is counted, so the
    surviving pairs are carried across as raw text rather than parsed and re-encoded: round-tripping
    them through urlencode turns "%20" into "+" and would hand a service something subtly different
    from what the announcement linked to. A link that is not http(s), or has no query, comes back
    unchanged.
    """
    if not url:
        return url
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.query:
        return url
    kept = [pair for pair in parts.query.split("&") if not is_tracking(unquote(pair.split("=", 1)[0]))]
    if len(kept) == len(parts.query.split("&")):
        return url
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "&".join(kept), parts.fragment))


def fits(url: str, limit: int = MAX_URL_LENGTH) -> bool:
    """Whether the site can store this link at all."""
    return len(url) <= limit


# A Telegram channel's web feed: t.me/s/<channel>, and the channel page itself, t.me/<channel>.
# A post inside it -- t.me/<channel>/<id> -- is a specific announcement and is not matched.
_TELEGRAM_FEED = re.compile(r"^/(?:s/)?[A-Za-z0-9_]{5,32}/?$")


def announces_one_event(url: str) -> bool:
    """Whether this address is the announcement of a single event, rather than a list of many.

    A source is read to find events, and when the model finds no link of its own the address the
    text came from is the obvious stand-in. That works for an organizer whose site is one race. It
    fails for the addresses that are themselves lists -- a forum index, a Telegram channel feed, a
    calendar's front page: a reader who follows one of those lands among dozens of announcements
    with no way to tell which was meant, which is worse than no link at all.

    What is judged is the address, not which section of the sources file it was written in: the
    same forum is a listing whether it was filed under organizers or aggregators.
    """
    if not url:
        return False
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return False
    path = parts.path or "/"
    host = parts.netloc.lower().removeprefix("www.")
    if host in ("t.me", "telegram.me"):
        return not _TELEGRAM_FEED.match(path)
    # A bare host announces nothing in particular -- it is whatever the site puts on its front page
    # today, and by the time anyone follows the link the announcement has scrolled off it.
    if path.strip("/") == "":
        return False
    return True
