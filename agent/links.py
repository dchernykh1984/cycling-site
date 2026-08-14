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

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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

    Anything that is not a recognised tracker is kept, in the order it was written: a query is how a
    page is chosen as often as it is how a click is counted, and dropping the wrong one would send
    the reader somewhere else. A link that is not http(s), or carries no query, comes back unchanged.
    """
    if not url:
        return url
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.query:
        return url
    kept = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if not is_tracking(key)]
    if len(kept) == len(parse_qsl(parts.query, keep_blank_values=True)):
        return url
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment))


def fits(url: str, limit: int = MAX_URL_LENGTH) -> bool:
    """Whether the site can store this link at all."""
    return len(url) <= limit
