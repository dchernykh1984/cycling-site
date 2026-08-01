"""Read an Instagram account's recent posts. Network I/O, coverage-omitted.

Only what a logged-out browser is served: the profile endpoint the web client itself calls, which
answers with the account's public metadata and its most recent posts. Nothing is posted, no account
is logged in, and one request per account per run is all a run makes.

Two things this deliberately does not do. It does not follow pagination -- a night's worth of
announcements fits in the page Instagram returns, and asking for more is what turns a polite reader
into something that gets blocked. And it does not touch accounts that are not professional: those
answer with nothing useful, which the caller reports rather than retries.

The parsing (:func:`posts_from_profile`, :func:`account_text`) is kept separate from the request so
it can be unit-tested against a recorded reply.
"""

from __future__ import annotations

import datetime
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from instagram_agent.accounts import Account

_PROFILE_URL = "https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
# The web client identifies itself with this application id; without it the endpoint answers with
# the logged-out shell instead of the profile.
_WEB_APP_ID = "936619743392459"
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
_TIMEOUT = 30
# Instagram answers a burst of requests with an error, and a nightly run has all the time it needs,
# so accounts are read one at a time with a pause between them.
_PAUSE_BETWEEN_ACCOUNTS = 20
_MAX_CAPTION_CHARS = 2000

# Statuses that mean "not now" rather than "not this account": rate limiting (Instagram answers it
# as 401 "please wait a few minutes" as often as 429) and its own gateway errors. Worth waiting out,
# because the alternative is losing a whole account for a night over a passing refusal.
_TRANSIENT_STATUSES = frozenset({401, 429, 500, 502, 503, 504})
_RETRIES = 3
_RETRY_BACKOFF = (30, 90)  # seconds before the second and third attempts

# Instagram fails to serialize some professional accounts and answers 400 with this. It is a fault
# on their side, has nothing to do with the request, and clears up on its own -- so an account that
# answers this is kept in the list and simply skipped for the night.
_THEIR_BUG = "ig_business_category_subvertical"


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


def _caption_of(node: dict) -> str:
    edges = (node.get("edge_media_to_caption") or {}).get("edges") or []
    for edge in edges:
        text = ((edge or {}).get("node") or {}).get("text") or ""
        if text.strip():
            return text.strip()[:_MAX_CAPTION_CHARS]
    return ""


def posts_from_profile(payload: dict) -> list[Post]:
    """The posts in a profile reply, newest first. Anything malformed is skipped, not raised.

    Instagram returns pinned posts ahead of the rest whatever their age, so the reply is not in date
    order: an account with a pinned post from May opens with it. Sorting here is what makes "the
    newest N posts" mean that, instead of spending the budget on whatever the club pinned.
    """
    user = ((payload or {}).get("data") or {}).get("user") or {}
    edges = (user.get("edge_owner_to_timeline_media") or {}).get("edges") or []
    posts: list[Post] = []
    for edge in edges:
        node = (edge or {}).get("node") or {}
        shortcode, taken_at = node.get("shortcode"), node.get("taken_at_timestamp")
        if not shortcode or not isinstance(taken_at, (int, float)):
            continue
        posts.append(
            Post(
                shortcode=str(shortcode),
                caption=_caption_of(node),
                published=datetime.datetime.fromtimestamp(taken_at, datetime.UTC).date(),
                is_video=bool(node.get("is_video")),
            )
        )
    return sorted(posts, key=lambda post: post.published, reverse=True)


def is_professional(payload: dict) -> bool:
    user = ((payload or {}).get("data") or {}).get("user") or {}
    return bool(user.get("is_professional_account") or user.get("is_business_account"))


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


def _get(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "X-IG-App-ID": _WEB_APP_ID,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Fetch-Site": "same-origin",
            "Referer": "https://www.instagram.com/",
        },
    )
    with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def _get_with_retries(url: str) -> dict:
    """Fetch, waiting out a refusal that says "not now" rather than "not this account"."""
    for attempt in range(_RETRIES):
        try:
            return _get(url)
        except urllib.error.HTTPError as exc:
            body = _error_body(exc)
            if _THEIR_BUG in body:
                raise AccountUnavailableError(
                    f"HTTP {exc.code}: Instagram could not serialize this account (its own error, "
                    f"not the request); it usually clears up on its own"
                ) from exc
            last = exc.code not in _TRANSIENT_STATUSES or attempt == _RETRIES - 1
            if last:
                raise AccountUnavailableError(f"HTTP {exc.code}{_hint_for(exc.code)}") from exc
            time.sleep(_RETRY_BACKOFF[attempt])
        except Exception as exc:  # network, DNS, malformed JSON
            if attempt == _RETRIES - 1:
                raise AccountUnavailableError(str(exc)) from exc
            time.sleep(_RETRY_BACKOFF[attempt])
    raise AccountUnavailableError("no attempt succeeded")  # unreachable, kept for the type checker


def _error_body(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", "replace")[:500]
    except Exception:
        return ""


def _hint_for(status: int) -> str:
    if status in (401, 429):
        return " (rate limited -- Instagram refuses this address for now)"
    if status == 404:
        return " (no such account)"
    return ""


def fetch_posts(account: Account) -> list[Post]:
    """The account's recent posts. Raises AccountUnavailableError with why, rather than returning [].

    An empty list is a real answer (an account that has posted nothing lately) and must not be
    confused with an account that could not be read at all.
    """
    payload = _get_with_retries(_PROFILE_URL.format(username=account.username))
    user = ((payload or {}).get("data") or {}).get("user")
    if not user:
        raise AccountUnavailableError("no profile in the reply")
    if user.get("is_private"):
        raise AccountUnavailableError("the account is private")
    if not is_professional(payload):
        raise AccountUnavailableError("not a professional account, so its posts are not readable")
    return posts_from_profile(payload)


def pause_between_accounts() -> None:
    time.sleep(_PAUSE_BETWEEN_ACCOUNTS)
