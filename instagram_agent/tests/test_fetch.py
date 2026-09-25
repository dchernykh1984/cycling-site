"""Turning a business_discovery reply into the posts, and the posts into the text the model reads."""

import datetime
import json

import pytest

from instagram_agent.accounts import Account
from instagram_agent.fetch import (
    AccountUnavailableError,
    account_text,
    business_discovery_url,
    fetch_posts,
    posts_from_business_discovery,
)

TODAY = datetime.date(2026, 8, 1)
USER_ID = "17841400000000000"
TOKEN = "EAAG-long-lived-token"
VERSION = "v21.0"


def _media(shortcode, caption, when, media_type="IMAGE", permalink=None):
    return {
        "caption": caption,
        "timestamp": datetime.datetime.combine(when, datetime.time(12), datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S%z"),
        "permalink": permalink or f"https://www.instagram.com/p/{shortcode}/",
        "media_type": media_type,
    }


def _payload(*media, username="someone"):
    return {"business_discovery": {"username": username, "media": {"data": list(media)}}, "id": USER_ID}


def test_a_post_carries_its_caption_date_and_permalink():
    posts = posts_from_business_discovery(_payload(_media("Abc123", "Early bird ride", datetime.date(2026, 7, 31))))
    assert len(posts) == 1
    assert posts[0].caption == "Early bird ride"
    assert posts[0].published == datetime.date(2026, 7, 31)
    assert posts[0].permalink == "https://www.instagram.com/p/Abc123/"


def test_a_reel_is_read_like_any_other_post():
    """Graph gives a reel its own permalink prefix; the shortcode is what we keep."""
    reel = _media(
        "Reel99", "ride video", datetime.date(2026, 7, 30), "VIDEO", permalink="https://www.instagram.com/reel/Reel99/"
    )
    posts = posts_from_business_discovery(_payload(reel))
    assert [(p.shortcode, p.is_video) for p in posts] == [("Reel99", True)]


def test_a_post_without_a_caption_is_kept_with_an_empty_one():
    node = _media("NoCap", None, datetime.date(2026, 7, 31))
    node["caption"] = None
    assert posts_from_business_discovery(_payload(node))[0].caption == ""


def test_a_malformed_post_is_skipped_rather_than_sinking_the_account():
    good = _media("Good1", "ride", datetime.date(2026, 7, 31))
    assert [p.shortcode for p in posts_from_business_discovery(_payload({"caption": "x"}, good))] == ["Good1"]


def test_a_timestamp_graph_did_not_send_in_its_own_format_is_skipped():
    broken = _media("Bad1", "ride", datetime.date(2026, 7, 31))
    broken["timestamp"] = "yesterday"
    assert posts_from_business_discovery(_payload(broken)) == []


def test_an_empty_or_broken_reply_yields_no_posts():
    assert posts_from_business_discovery({}) == []
    assert posts_from_business_discovery({"business_discovery": {}}) == []


def test_posts_come_back_newest_first_whatever_the_club_pinned():
    old = _media("Pinned", "pinned in May", datetime.date(2026, 5, 1))
    new = _media("Fresh", "this week", datetime.date(2026, 7, 31))
    assert [p.shortcode for p in posts_from_business_discovery(_payload(old, new))] == ["Fresh", "Pinned"]


def test_the_text_gives_every_post_its_publication_date_and_link():
    post = _media("Abc123", "this Saturday we ride", datetime.date(2026, 7, 30))
    posts = posts_from_business_discovery(_payload(post))
    text = account_text(Account("ubtalmaty"), posts, recent_days=21, today=TODAY)
    assert "2026-07-30" in text
    assert "https://www.instagram.com/p/Abc123/" in text
    assert "this Saturday we ride" in text


def test_the_text_carries_the_maintainers_hint_and_city():
    account = Account("ubtalmaty", hint="an Almaty road club", city="Almaty")
    text = account_text(account, [], recent_days=21, today=TODAY)
    assert "an Almaty road club" in text
    assert "Almaty" in text


def test_posts_older_than_the_window_are_left_out():
    posts = posts_from_business_discovery(
        _payload(
            _media("New", "this Saturday we ride", datetime.date(2026, 7, 30)),
            _media("Old", "a ride from last winter", datetime.date(2026, 1, 5)),
        )
    )
    text = account_text(Account("ubtalmaty"), posts, recent_days=21, today=TODAY)
    assert "this Saturday we ride" in text
    assert "a ride from last winter" not in text


# --------------------------------------------------------------------------- the request


def test_the_url_asks_for_everything_in_one_call():
    """Graph refuses to serve the media ids it hands back, so what is not nested here is lost."""
    url = business_discovery_url(USER_ID, "romantic_dc", VERSION, 10)
    assert url.startswith(f"https://graph.facebook.com/{VERSION}/{USER_ID}?")
    for wanted in ("business_discovery.username", "romantic_dc", "caption", "timestamp", "permalink", "media_type"):
        assert wanted in url
    assert TOKEN not in url  # the token travels as a header, never in the query string


def _answering(*replies):
    remaining = list(replies)

    def _request(url, token):
        return remaining.pop(0) if remaining else (200, "{}")

    return _request


def _with_transport(request, *, token=TOKEN, user_id=USER_ID):
    import instagram_agent.fetch as module

    original = module._request
    module._request = request
    try:
        return fetch_posts(Account("someone"), user_id, token, VERSION, 10)
    finally:
        module._request = original


def test_a_readable_account_gives_up_its_posts():
    reply = json.dumps(_payload(_media("Ok1", "this Saturday we ride", datetime.date(2026, 7, 31))))
    assert [p.shortcode for p in _with_transport(_answering((200, reply)))] == ["Ok1"]


def test_without_credentials_it_says_so_instead_of_asking():
    """The logged-out endpoint is gone, so a run with no token cannot succeed -- say why, up front."""
    asked: list = []

    def _request(url, token):
        asked.append(url)
        return 200, "{}"

    with pytest.raises(AccountUnavailableError, match="IG_GRAPH_TOKEN"):
        _with_transport(_request, token="")
    with pytest.raises(AccountUnavailableError, match="IG_GRAPH_USER_ID"):
        _with_transport(_request, user_id="")
    assert asked == []


def test_an_account_graph_will_not_discover_says_why():
    """No business_discovery in a 200 is what a personal or renamed account looks like."""
    with pytest.raises(AccountUnavailableError, match="not professional"):
        _with_transport(_answering((200, json.dumps({"id": USER_ID}))))


def test_graphs_own_message_is_repeated_rather_than_just_the_status():
    body = json.dumps({"error": {"message": "Unsupported get request.", "code": 100}})
    with pytest.raises(AccountUnavailableError, match="Unsupported get request"):
        _with_transport(_answering((400, body)))


def test_an_expired_token_is_reported_with_what_graph_said():
    body = json.dumps({"error": {"message": "Error validating access token: Session has expired"}})
    with pytest.raises(AccountUnavailableError, match="Session has expired"):
        _with_transport(_answering((401, body)))


def test_a_refusal_is_reported_rather_than_asked_again():
    """A second attempt from the same machine seconds later is the same request; the next run asks."""
    asked: list = []

    def _request(url, token):
        asked.append(url)
        return 429, ""

    with pytest.raises(AccountUnavailableError, match="refused this time"):
        _with_transport(_request)
    assert len(asked) == 1


def test_instagrams_own_serialization_error_is_named_as_theirs():
    """A 400 about the account's business category is their bug, not something we did."""
    body = '{"error":{"message":"Asset asset://laser.provider/ig_business_category_subvertical deleted"}}'
    with pytest.raises(AccountUnavailableError, match="its own error"):
        _with_transport(_answering((400, body)))


def test_a_reply_that_is_not_json_is_reported_as_such():
    with pytest.raises(AccountUnavailableError, match="not JSON"):
        _with_transport(_answering((200, "<html>maintenance</html>")))


def test_the_token_never_reaches_an_error_message():
    """Build logs for this repository are public, and curl quotes back what it was given."""
    from instagram_agent.fetch import _without_secrets

    assert TOKEN not in _without_secrets(f"curl: (6) could not resolve {TOKEN}", TOKEN)
