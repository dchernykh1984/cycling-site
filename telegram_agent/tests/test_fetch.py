"""The pure halves of reading a channel: ref arithmetic and turning messages into prompt text."""

import datetime

from telegram_agent.channels import Channel
from telegram_agent.fetch import (
    MESSAGES_PER_PROMPT,
    Message,
    channel_text,
    in_batches,
    internal_id,
    invite_hash,
    reading_note,
    worth_reading,
)

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
    text = channel_text(channel, [], recent_hours=25, today=TODAY)
    assert "Telegram channel: @almatyriders" in text
    assert "a club chat" in text
    assert "Almaty" in text
    assert "Today is 2026-08-02" in text


def test_each_message_carries_the_date_it_was_published():
    """That date is what turns an announcement's "this Saturday" into a real day."""
    text = channel_text(Channel(ref="+abc"), [_message("ride tomorrow", days_ago=2)], 25, TODAY)
    assert "--- published 2026-07-31" in text
    assert "ride tomorrow" in text


def test_the_window_is_stated_in_hours_because_the_run_is_nightly():
    text = channel_text(Channel(ref="+abc"), [_message("fresh")], recent_hours=25, today=TODAY)
    assert "last 25 hours" in text


def test_a_message_arrives_already_flattened_for_the_prompt():
    text = channel_text(Channel(ref="+abc"), [Message(text="ride at 7:00", published=TODAY)], 25, TODAY)
    assert "ride at 7:00" in text


def test_no_link_of_any_kind_is_offered_to_the_model():
    """A private announcement has no address the public could open, so none is invented."""
    text = channel_text(Channel(ref="c/1949598843"), [_message("ride tomorrow")], 25, TODAY)
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


def test_the_reading_note_says_how_much_of_the_channel_was_seen():
    """The line that tells "no announcements" apart from "the run barely saw the channel"."""
    messages = [_message("a", days_ago=0), _message("b", days_ago=1)]
    note = reading_note("@almatyriders", messages, recent_hours=25, capped=False)
    assert "read 2 messages of the last 25h" in note
    assert "back to 2026-08-01" in note
    assert "CAPPED" not in note
    assert "no messages worth reading in the last 25h" in reading_note("+abc", [], 25, False)


def test_a_capped_read_says_so_rather_than_looking_like_a_quiet_night():
    """Silent truncation reads exactly like "the channel had nothing to say"."""
    note = reading_note("@chatty", [_message("a")], recent_hours=250, capped=True)
    assert "CAPPED" in note
    assert "older messages in the window were not read" in note


# --- what is worth handing to the model ---------------------------------------------------------


def test_a_message_too_short_to_be_an_announcement_is_dropped():
    """A group chat is full of these, and each one spends prompt on nothing."""
    for junk in ("+", "Da", "Spasibo", "ok", "   ", "?"):
        assert not worth_reading(junk), junk


def test_a_real_announcement_is_kept():
    for real in ("Zavtra v 7:00 sbor u Halyk Bank", "Velosreda 05.08, start 18:20"):
        assert worth_reading(real), real


def test_length_is_measured_after_flattening_whitespace():
    assert not worth_reading("da" + " " * 40)


# --- batching -----------------------------------------------------------------------------------


def test_a_days_worth_of_chatter_becomes_several_prompts():
    """One huge prompt is not just costlier -- it is worse at finding the one announcement in it."""
    messages = [_message(f"message number {n}") for n in range(250)]
    batches = in_batches(messages)
    assert [len(b) for b in batches] == [MESSAGES_PER_PROMPT, MESSAGES_PER_PROMPT, 50]
    assert sum(len(b) for b in batches) == 250, "no message may be lost between batches"


def test_the_model_reads_a_chat_in_the_order_it_was_written():
    """Telegram hands messages back newest first; a reply before its announcement reads backwards."""
    newest_first = [
        Message(text="a reply to the announcement", published=TODAY),
        Message(text="the announcement itself", published=TODAY - datetime.timedelta(days=1)),
    ]
    assert [m.text for m in in_batches(newest_first)[0]] == [
        "the announcement itself",
        "a reply to the announcement",
    ]


def test_the_oldest_messages_are_in_the_first_batch():
    messages = [_message(f"message number {n}") for n in range(150)]
    batches = in_batches(messages)
    assert batches[0][0].text == "message number 149", "the oldest message opens the first prompt"
    assert batches[-1][-1].text == "message number 0", "the newest closes the last"


def test_a_quiet_channel_is_one_prompt_and_an_empty_one_is_none():
    assert len(in_batches([_message("only one")])) == 1
    assert in_batches([]) == []


def test_a_vanished_username_is_reported_as_unreadable_not_raised_raw(monkeypatch):
    """Telethon wraps UsernameNotOccupiedError into a bare ValueError; entity_of must still turn
    it into the per-channel report. Measured live on a group that went private."""
    import sys
    import types

    import pytest

    from telegram_agent.fetch import ChannelUnavailableError, entity_of

    errors = types.ModuleType("telethon.errors")
    for name in (
        "ChannelPrivateError",
        "InviteHashExpiredError",
        "InviteHashInvalidError",
        "UsernameInvalidError",
        "UsernameNotOccupiedError",
        "FloodWaitError",
    ):
        setattr(errors, name, type(name, (Exception,), {}))
    functions_messages = types.ModuleType("telethon.tl.functions.messages")
    functions_messages.CheckChatInviteRequest = type("CheckChatInviteRequest", (), {})
    tl_types = types.ModuleType("telethon.tl.types")
    tl_types.ChatInviteAlready = type("ChatInviteAlready", (), {})
    for name, module in {
        "telethon": types.ModuleType("telethon"),
        "telethon.errors": errors,
        "telethon.tl": types.ModuleType("telethon.tl"),
        "telethon.tl.functions": types.ModuleType("telethon.tl.functions"),
        "telethon.tl.functions.messages": functions_messages,
        "telethon.tl.types": tl_types,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    class _Client:
        def get_entity(self, ref):
            raise ValueError(f'No user has "{ref}" as username')

    with pytest.raises(ChannelUnavailableError, match="username is not in use"):
        entity_of(_Client(), Channel(ref="@gone_private"))
