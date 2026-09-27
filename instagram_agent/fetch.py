"""Read an Instagram account's recent posts. Network I/O, coverage-omitted.

Through Meta's own Graph API, using the `business_discovery` edge: one professional account asks
for another professional account's public posts, which is the documented way to do this and the
only one left. The endpoint a logged-out browser used to be served
(`/api/v1/users/web_profile_info/`) now answers `401 {"require_login": true}` to everybody -- it
did so on every nightly run for three weeks before this was written -- and the public profile page
is a script shell carrying no posts at all, so there is nothing to fall back to.

What that costs: credentials. A run needs an Instagram Business or Creator account of our own
(IG_GRAPH_USER_ID) and a long-lived token for it (IG_GRAPH_TOKEN). Without them this reader says so
plainly rather than making a request that cannot succeed.

The token is sent as an Authorization header, never in the query string: curl quotes the URL back
in its own error text, and a token in the URL would be printed into a public build log the first
time DNS hiccuped.

Two things this deliberately does not do. It does not follow pagination -- a night's worth of
announcements fits in the first page, and asking for more is what turns a polite reader into
something that gets blocked. And it does not retry: a second attempt from the same machine, seconds
later, is the same request and gets the same answer.

The parsing (:func:`posts_from_business_discovery`, :func:`account_text`) is kept separate from the
request so it can be unit-tested against a recorded reply.
"""

from __future__ import annotations

import datetime
import json
import re
import shutil
import subprocess
import tempfile
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

from instagram_agent.accounts import Account

_GRAPH_HOST = "https://graph.facebook.com"
# Pinned rather than floating: Meta supports a version for about two years and changes field shapes
# between them, so a run should keep reading the same shape until somebody chooses to move it.
# IG_GRAPH_VERSION overrides it without a code change when that day comes.
DEFAULT_GRAPH_VERSION = "v21.0"
_USER_AGENT = "universalbicycle.team events agent"
_TIMEOUT = 30
_MAX_CAPTION_CHARS = 2000

# Instagram fails to serialize some professional accounts and answers 400 quoting this asset. It is
# a fault on their side, has nothing to do with the request, and clears up on its own.
_THEIR_BUG = "ig_business_category_subvertical"

# A permalink is the only place the post's own id appears in a business_discovery reply. Reels and
# IGTV items carry their own prefix; the shortcode is what matters and /p/ resolves to all of them.
_SHORTCODE = re.compile(r"/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)")


class AccountUnavailableError(Exception):
    """The account could not be read: private, personal, renamed, or refused by Instagram."""


@dataclass(frozen=True)
class Post:
    """One published post, as far as an event announcement is concerned."""

    shortcode: str
    caption: str
    published: datetime.date
    is_video: bool = False

    @property
    def permalink(self) -> str:
        return f"https://www.instagram.com/p/{self.shortcode}/"


def posts_from_business_discovery(payload: dict) -> list[Post]:
    """The posts in a business_discovery reply, newest first. Anything malformed is skipped.

    Sorted here rather than trusted: the old web endpoint hoisted pinned posts above everything
    else whatever their age, and whether Graph does the same is not something this code should
    have to know. Sorting costs nothing on a page of ten and makes "the newest N posts" mean that
    however the reply happens to be ordered.
    """
    discovery = (payload or {}).get("business_discovery") or {}
    media = (discovery.get("media") or {}).get("data") or []
    posts: list[Post] = []
    for node in media:
        if not isinstance(node, dict):
            continue
        found = _SHORTCODE.search(str(node.get("permalink") or ""))
        published = _published_on(node.get("timestamp"))
        if not found or published is None:
            continue
        caption = str(node.get("caption") or "").strip()[:_MAX_CAPTION_CHARS]
        posts.append(
            Post(
                shortcode=found.group(1),
                caption=caption,
                published=published,
                is_video=str(node.get("media_type") or "").upper() == "VIDEO",
            )
        )
    return sorted(posts, key=lambda post: post.published, reverse=True)


def _published_on(stamp: object) -> datetime.date | None:
    """The date out of Graph's timestamp ("2026-09-24T17:05:00+0000"), or None if it is not one."""
    if not isinstance(stamp, str):
        return None
    try:
        return datetime.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S%z").date()
    except ValueError:
        return None


def account_text(account: Account, posts: list[Post], recent_days: int, today: datetime.date) -> str:
    """The account's recent posts as the text the model reads.

    Every post carries the date it was published, because that is what makes a caption's "this
    Saturday" a real date; and its permalink, because that is the only link an announcement has.
    """
    lines = [f"Instagram account: @{account.username}"]
    if account.hint:
        lines.append(f"What the maintainers know about it: {account.hint}")
    if account.city:
        lines.append(f"This club rides in: {account.city}")
    lines.append(f"Today is {today.isoformat()}. Posts published in the last {recent_days} days:")
    for post in posts:
        if (today - post.published).days > recent_days:
            continue
        caption = " ".join(post.caption.split()) if post.caption else "(no caption)"
        lines.append(f"\n--- published {post.published.isoformat()} | {post.permalink}\n{caption}")
    return "\n".join(lines)


def _request(url: str, token: str) -> tuple[int, str]:
    """GET the url with curl, returning (status, body). The token travels as a header.

    With curl, and not Python's own client, for a reason worth keeping: measured side by side on the
    same runners in the same minute, curl was answered 3 times out of 3 and urllib refused 3 out of
    3 with HTTP 429. The address, the headers and the account were identical, so what is being
    turned away is the client itself -- Python's TLS handshake is recognisable and, from a cloud
    address, enough on its own to be refused. Shelling out avoids adding a binary dependency
    (curl_cffi and friends) for one request a night.
    """
    curl = shutil.which("curl")
    if not curl:
        raise AccountUnavailableError("curl is not installed, and it is what Instagram answers")
    with tempfile.TemporaryDirectory() as workspace:
        body_file = Path(workspace) / "body"
        finished = subprocess.run(  # noqa: S603 -- fixed argv, no shell, url built from a username
            [
                curl,
                "--silent",
                "--show-error",
                "--max-time",
                str(_TIMEOUT),
                "--output",
                str(body_file),
                "--write-out",
                "%{http_code}",
                "--header",
                f"User-Agent: {_USER_AGENT}",
                "--header",
                f"Authorization: Bearer {token}",
                "--header",
                "Accept-Language: en-US,en;q=0.9",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT + 10,
        )
        if finished.returncode != 0:
            said = _without_secrets(finished.stderr.strip(), token) or finished.returncode
            raise AccountUnavailableError(f"curl failed: {said}")
        status = int(finished.stdout.strip() or 0)
        return status, body_file.read_text(encoding="utf-8", errors="replace")


def _without_secrets(text: str, token: str) -> str:
    """Never let the token reach a log. Build logs for this repository are public."""
    return text.replace(token, "<token>") if token else text


def _get_once(url: str, token: str) -> dict:
    """Fetch once, turning every failure into AccountUnavailableError with why it failed.

    Once, and never again in the same run: a second attempt from the same machine, seconds later,
    is the same request and gets the same answer. Tomorrow's run starts fresh.
    """
    status, body = _request(url, token)
    payload: dict = {}
    if body:
        try:
            payload = json.loads(body)
        except ValueError as exc:
            if status == 200:
                raise AccountUnavailableError(f"the reply was not JSON: {exc}") from exc
            payload = {}
    # Graph answers a refusal as JSON with its own message, which says far more than the status --
    # "Unsupported get request" is what an account that is not professional looks like.
    said = (payload.get("error") or {}).get("message") if isinstance(payload, dict) else None
    if status == 200 and not said:
        return payload
    if _THEIR_BUG in body:
        raise AccountUnavailableError(
            f"HTTP {status}: Instagram could not serialize this account (its own error, not the "
            f"request); it usually clears up on its own"
        )
    detail = f": {_without_secrets(str(said), token)}" if said else _hint_for(status)
    raise AccountUnavailableError(f"HTTP {status}{detail}")


def _hint_for(status: int) -> str:
    if status in (401, 429):
        return " (refused this time; the next run asks again)"
    if status == 404:
        return " (no such account)"
    return ""


def business_discovery_url(user_id: str, username: str, version: str, limit: int) -> str:
    """The one request a run makes for an account.

    Field expansion in a single call is not a nicety here: Graph refuses to serve the media ids a
    business_discovery reply hands back if you ask for them separately, so what is not nested in
    this URL cannot be fetched at all afterwards.
    """
    fields = (
        f"business_discovery.username({username})"
        f"{{username,media_count,media.limit({max(limit, 1)})"
        f"{{caption,timestamp,permalink,media_type}}}}"
    )
    return f"{_GRAPH_HOST}/{version}/{urllib.parse.quote(user_id)}?{urllib.parse.urlencode({'fields': fields})}"


def fetch_posts(account: Account, user_id: str, token: str, version: str, limit: int) -> list[Post]:
    """The account's recent posts. Raises AccountUnavailableError with why, rather than returning [].

    An empty list is a real answer (an account that has posted nothing lately) and must not be
    confused with an account that could not be read at all.
    """
    if not token or not user_id:
        raise AccountUnavailableError(
            "no Graph API credentials: set IG_GRAPH_USER_ID and IG_GRAPH_TOKEN. Instagram closed "
            "the logged-out endpoint this reader used before, so there is no way round them"
        )
    payload = _get_once(business_discovery_url(user_id, account.username, version, limit), token)
    discovery = (payload or {}).get("business_discovery")
    if not discovery:
        raise AccountUnavailableError(
            "no business_discovery in the reply, which is what Graph returns for an account that "
            "is not professional, has been renamed, or is age-gated"
        )
    return posts_from_business_discovery(payload)
