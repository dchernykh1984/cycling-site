"""Read an Instagram account's recent posts. Network I/O, coverage-omitted.

Only what a logged-out browser is served: the profile endpoint the web client itself calls, which
answers with the account's public metadata and its most recent posts. Nothing is posted, no account
is logged in, and one request per account per run is all a run makes.

The request is made with curl rather than Python's own client, and that is not incidental: measured
side by side on the same machines in the same minute, curl was answered every time and urllib was
refused every time with HTTP 429. Same address, same headers, same account -- what gets turned away
is the client itself.

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
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from instagram_agent.accounts import Account

_PROFILE_URL = "https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
# The web client identifies itself with this application id; without it the endpoint answers with
# the logged-out shell instead of the profile.
_WEB_APP_ID = "936619743392459"
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
_TIMEOUT = 30
_MAX_CAPTION_CHARS = 2000

# Instagram fails to serialize some professional accounts and answers 400 quoting this asset. It is
# a fault on their side, has nothing to do with the request, and clears up on its own.
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


def _request(url: str) -> tuple[int, str]:
    """GET the url with curl, returning (status, body).

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
                f"X-IG-App-ID: {_WEB_APP_ID}",
                "--header",
                "Accept-Language: en-US,en;q=0.9",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT + 10,
        )
        if finished.returncode != 0:
            raise AccountUnavailableError(f"curl failed: {finished.stderr.strip() or finished.returncode}")
        status = int(finished.stdout.strip() or 0)
        return status, body_file.read_text(encoding="utf-8", errors="replace")


def _get_once(url: str) -> dict:
    """Fetch once, turning every failure into AccountUnavailableError with why it failed.

    Once, and never again in the same run: a second attempt from the same machine, seconds later,
    is the same request and gets the same answer. Tomorrow's run starts fresh.
    """
    status, body = _request(url)
    if status == 200:
        try:
            return json.loads(body)
        except ValueError as exc:
            raise AccountUnavailableError(f"the reply was not JSON: {exc}") from exc
    if _THEIR_BUG in body:
        raise AccountUnavailableError(
            f"HTTP {status}: Instagram could not serialize this account (its own error, not the "
            f"request); it usually clears up on its own"
        )
    raise AccountUnavailableError(f"HTTP {status}{_hint_for(status)}")


def _hint_for(status: int) -> str:
    if status in (401, 429):
        return " (refused this time; the next run asks again)"
    if status == 404:
        return " (no such account)"
    return ""


def fetch_posts(account: Account) -> list[Post]:
    """The account's recent posts. Raises AccountUnavailableError with why, rather than returning [].

    An empty list is a real answer (an account that has posted nothing lately) and must not be
    confused with an account that could not be read at all.
    """
    payload = _get_once(_PROFILE_URL.format(username=account.username))
    user = ((payload or {}).get("data") or {}).get("user")
    if not user:
        raise AccountUnavailableError("no profile in the reply")
    if user.get("is_private"):
        raise AccountUnavailableError("the account is private")
    if not is_professional(payload):
        raise AccountUnavailableError("not a professional account, so its posts are not readable")
    return posts_from_profile(payload)
