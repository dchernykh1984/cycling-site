"""An event points at the post it was announced in, not at the channel.

Until this existed the Telegram agent published no announcement link at all -- every t.me address
the model wrote was scrubbed, and the message's own number was never read, so there was nothing to
link. The maintainer pasted the links by hand afterwards (events 526, 537, 541, 624).
"""

import datetime

import pytest

from agent.models import Candidate
from telegram_agent.channels import post_link
from telegram_agent.fetch import Message, topic_id
from telegram_agent.run import _scrubbed, _with_post_link

TODAY = datetime.date(2026, 8, 28)


class _Reply:
    def __init__(self, forum_topic=False, top_id=None, msg_id=None):
        self.forum_topic = forum_topic
        self.reply_to_top_id = top_id
        self.reply_to_msg_id = msg_id


class _Item:
    def __init__(self, reply=None):
        self.reply_to = reply


class TestPostLink:
    def test_a_public_channel_is_addressed_by_its_handle(self):
        assert post_link("@mystartkz", 951) == "https://t.me/mystartkz/951"

    def test_a_private_channel_is_addressed_by_its_internal_id(self):
        """The form Telegram itself copies from inside the chat: it opens the post for a member
        and shows nothing to anyone else."""
        assert post_link("c/1949598843", 93485) == "https://t.me/c/1949598843/93485"

    def test_an_invite_ref_uses_the_chat_id_read_when_the_channel_was_opened(self):
        assert post_link("+AbCdEf", 42, chat_id=1949598843) == "https://t.me/c/1949598843/42"

    def test_an_invite_ref_with_no_chat_id_yields_nothing_rather_than_a_guess(self):
        assert post_link("+AbCdEf", 42) == ""

    def test_a_forum_topic_sits_between_the_chat_and_the_message(self):
        assert post_link("c/1949598843", 93868, topic_id=47898) == "https://t.me/c/1949598843/47898/93868"
        assert post_link("@freemindalmaty", 4123, topic_id=716) == "https://t.me/freemindalmaty/716/4123"

    def test_a_message_with_no_number_yields_nothing(self):
        assert post_link("@mystartkz", 0) == ""


class TestTopicOfAMessage:
    def test_an_ordinary_chat_has_no_topic(self):
        assert topic_id(_Item()) is None

    def test_a_quoted_message_in_an_ordinary_chat_is_not_a_topic(self):
        """reply_to_msg_id means the quoted message here; only a forum header makes it a topic."""
        assert topic_id(_Item(_Reply(forum_topic=False, msg_id=500))) is None

    def test_a_message_posted_straight_into_a_topic(self):
        assert topic_id(_Item(_Reply(forum_topic=True, msg_id=47898))) == 47898

    def test_a_reply_inside_a_topic_names_the_topic_not_the_message_it_answers(self):
        assert topic_id(_Item(_Reply(forum_topic=True, top_id=47898, msg_id=93800))) == 47898


class TestCandidateGetsTheLink:
    def _messages(self):
        return {
            93485: Message(text="hike on saturday", published=TODAY, id=93485, link="https://t.me/c/1949598843/93485"),
        }

    def _candidate(self, **kwargs):
        return Candidate(title="Hike", date_start="2026-08-29", **kwargs)

    def test_the_named_message_becomes_the_announcement_link(self):
        got = _with_post_link(self._candidate(source_message_id=93485), self._messages())
        assert got.source_url == "https://t.me/c/1949598843/93485"

    def test_a_message_the_model_did_not_name_leaves_the_event_unlinked(self):
        got = _with_post_link(self._candidate(), self._messages())
        assert got.source_url == ""

    def test_a_number_from_another_batch_is_not_forced_into_a_link(self):
        got = _with_post_link(self._candidate(source_message_id=11111), self._messages())
        assert got.source_url == ""

    def test_the_link_survives_the_scrubbing_that_removes_the_models_own(self):
        """The scrub runs first and clears whatever address the model copied; ours is set after."""
        scrubbed = _scrubbed(self._candidate(source_message_id=93485, source_url="https://t.me/joinchat/SECRET"))
        assert scrubbed.source_url == ""
        assert _with_post_link(scrubbed, self._messages()).source_url == "https://t.me/c/1949598843/93485"


@pytest.mark.parametrize("ref", ["@mystartkz", "c/1949598843"])
def test_a_link_fits_the_column_the_site_stores_it_in(ref):
    from agent.links import MAX_URL_LENGTH

    assert len(post_link(ref, 99999999, topic_id=99999999)) <= MAX_URL_LENGTH
