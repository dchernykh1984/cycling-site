"""The pure halves of reading a channel: ref arithmetic and turning messages into prompt text."""

import datetime

from telegram_agent.channels import Channel
from telegram_agent.fetch import Message, channel_text, internal_id, invite_hash

TODAY = datetime.date(2026, 8, 2)


def _message(text, days_ago=1):
    return Message(text=text, published=TODAY - datetime.timedelta(days=days_ago))


def test_an_invite_ref_gives_up_its_bare_hash():
    assert invite_hash("+AbCdEfGhIjKlMnOp") == "AbCdEfGhIjKlMnOp"


def test_an_internal_ref_becomes_the_api_channel_id():
    """t.me/c/<id> carries the bare id; the API addresses the same channel as -100<id>."""
    assert internal_id("c/1949598843") == -1001949598843


def test_the_text_names_the_channel_its_hint_and_its_city():
    channel = Channel(ref="@almatyriders", hint="a club chat", city="Almaty")
    text = channel_text(channel, [], recent_days=21, today=TODAY)
    assert "Telegram channel: @almatyriders" in text
    assert "a club chat" in text
    assert "Almaty" in text
    assert "Today is 2026-08-02" in text


def test_each_message_carries_the_date_it_was_published():
    """That date is what turns an announcement's "this Saturday" into a real day."""
    text = channel_text(Channel(ref="+abc"), [_message("ride tomorrow", days_ago=2)], 21, TODAY)
    assert "--- published 2026-07-31" in text
    assert "ride tomorrow" in text


def test_messages_older_than_the_window_are_left_out():
    messages = [_message("fresh", days_ago=1), _message("stale", days_ago=30)]
    text = channel_text(Channel(ref="+abc"), messages, recent_days=21, today=TODAY)
    assert "fresh" in text
    assert "stale" not in text


def test_message_whitespace_is_flattened_for_the_prompt():
    text = channel_text(Channel(ref="+abc"), [_message("ride\n\nat  7:00")], 21, TODAY)
    assert "ride at 7:00" in text


def test_no_link_of_any_kind_is_offered_to_the_model():
    """A private announcement has no address the public could open, so none is invented."""
    text = channel_text(Channel(ref="c/1949598843"), [_message("ride tomorrow")], 21, TODAY)
    assert "https://" not in text
    assert "t.me" not in text


def test_the_model_is_not_handed_an_invite_hash_it_could_echo():
    """A public group is named; a private ref is a credential-like string the model must not see."""
    text = channel_text(Channel(ref="+AbCdEfGhIjKlMnOp"), [], 21, TODAY)
    assert "AbCdEfGhIjKlMnOp" not in text
    assert "(a private channel)" in text
    assert "Telegram channel: c/" not in channel_text(Channel(ref="c/1949598843"), [], 21, TODAY)
    assert "@almatyriders" in channel_text(Channel(ref="@almatyriders"), [], 21, TODAY)


def test_a_short_flood_wait_is_served_and_a_long_one_reported(monkeypatch):
    """Telegram hands out short waits routinely; a nightly run serves them instead of losing the channel."""
    import pytest

    from telegram_agent import fetch as module

    slept = []
    monkeypatch.setattr(module.time, "sleep", slept.append)
    module._sit_out(5)
    assert slept == [6], "a second on top, so the wait is truly over"
    with pytest.raises(module.ChannelUnavailableError, match="flood limit"):
        module._sit_out(300)
    assert slept == [6], "a long wait is never served"
