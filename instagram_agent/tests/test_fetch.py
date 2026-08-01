"""Turning a profile reply into the posts, and the posts into the text the model reads."""

import datetime

import pytest

from instagram_agent.accounts import Account
from instagram_agent.fetch import (
    AccountUnavailableError,
    account_text,
    fetch_posts,
    is_professional,
    posts_from_profile,
)

TODAY = datetime.date(2026, 8, 1)


def _payload(*posts, professional=True, private=False):
    return {
        "data": {
            "user": {
                "is_professional_account": professional,
                "is_private": private,
                "edge_owner_to_timeline_media": {"edges": [{"node": node} for node in posts]},
            }
        }
    }


def _node(shortcode, caption, when, is_video=False):
    stamp = int(datetime.datetime.combine(when, datetime.time(12), datetime.UTC).timestamp())
    return {
        "shortcode": shortcode,
        "taken_at_timestamp": stamp,
        "is_video": is_video,
        "edge_media_to_caption": {"edges": [{"node": {"text": caption}}]},
    }


def test_a_post_carries_its_caption_date_and_permalink():
    posts = posts_from_profile(_payload(_node("Abc123", "Early bird ride", datetime.date(2026, 7, 31))))
    assert len(posts) == 1
    assert posts[0].caption == "Early bird ride"
    assert posts[0].published == datetime.date(2026, 7, 31)
    assert posts[0].permalink == "https://www.instagram.com/p/Abc123/"


def test_a_post_without_a_caption_is_kept_with_an_empty_one():
    """An announcement is sometimes only a poster image -- the post still has to be visible."""
    node = _node("NoCap", "", datetime.date(2026, 7, 31))
    node["edge_media_to_caption"] = {"edges": []}
    assert posts_from_profile(_payload(node))[0].caption == ""


def test_a_malformed_post_is_skipped_rather_than_sinking_the_account():
    good = _node("Good1", "ride", datetime.date(2026, 7, 30))
    assert [p.shortcode for p in posts_from_profile(_payload({}, {"shortcode": "NoDate"}, good))] == ["Good1"]


def test_an_empty_or_broken_reply_yields_no_posts():
    assert posts_from_profile({}) == []
    assert posts_from_profile({"data": {}}) == []
    assert posts_from_profile({"data": {"user": {}}}) == []


def test_professional_accounts_are_recognised():
    assert is_professional(_payload(professional=True))
    assert not is_professional(_payload(professional=False))
    assert is_professional({"data": {"user": {"is_business_account": True}}})


def test_the_text_gives_every_post_its_publication_date_and_link():
    """ "This Saturday" is only a date next to the day the post was published."""
    posts = posts_from_profile(_payload(_node("Abc123", "In this Saturday we ride", datetime.date(2026, 7, 31))))
    text = account_text(Account("ubtalmaty"), posts, recent_days=21, today=TODAY)
    assert "published 2026-07-31" in text
    assert "https://www.instagram.com/p/Abc123/" in text
    assert "Today is 2026-08-01" in text
    assert "In this Saturday we ride" in text


def test_the_text_carries_the_maintainers_hint_and_city():
    account = Account("ubtalmaty", hint="announces a Saturday coffee ride", city="Almaty")
    text = account_text(account, [], recent_days=21, today=TODAY)
    assert "announces a Saturday coffee ride" in text
    assert "Almaty" in text


def test_posts_older_than_the_window_are_left_out():
    fresh = _node("Fresh1", "this Saturday we ride", datetime.date(2026, 7, 28))
    stale = _node("Stale1", "a ride from last winter", datetime.date(2026, 1, 5))
    text = account_text(Account("ubtalmaty"), posts_from_profile(_payload(fresh, stale)), 21, TODAY)
    assert "this Saturday we ride" in text
    assert "a ride from last winter" not in text


def test_an_account_that_cannot_be_read_says_why():
    """A run must tell "nothing announced" from "could not read it" -- they need different fixes."""

    class _Refused:
        def __init__(self, payload):
            self.payload = payload

    import instagram_agent.fetch as module

    original = module._get
    try:
        module._get = lambda url: _payload(professional=False)
        with pytest.raises(AccountUnavailableError, match="professional"):
            fetch_posts(Account("someone"))

        module._get = lambda url: _payload(private=True)
        with pytest.raises(AccountUnavailableError, match="private"):
            fetch_posts(Account("someone"))

        module._get = lambda url: {"data": {}}
        with pytest.raises(AccountUnavailableError, match="no profile"):
            fetch_posts(Account("someone"))
    finally:
        module._get = original


def test_a_pinned_old_post_does_not_come_first():
    """Instagram puts pinned posts ahead of the rest, so the reply is not in date order.

    Taken at face value, an account with a pinned post from spring spends a slot of the post budget
    on it before the announcements it actually published this week.
    """
    pinned = _node("Pinned", "our club, join us", datetime.date(2026, 5, 12))
    recent = _node("Recent", "this Saturday we ride", datetime.date(2026, 7, 31))
    older = _node("Older", "last month", datetime.date(2026, 6, 30))
    posts = posts_from_profile(_payload(pinned, recent, older))
    assert [p.shortcode for p in posts] == ["Recent", "Older", "Pinned"]
