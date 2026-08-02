"""Reading telegram_channels.yaml, which is edited by hand and so arrives in many shapes."""

from pathlib import Path

from telegram_agent.channels import parse_channels


def test_an_invite_link_keeps_its_hash():
    assert [c.ref for c in parse_channels("channels:\n  - https://t.me/+AbCdEfGhIjKlMnOp\n")] == ["+AbCdEfGhIjKlMnOp"]


def test_an_old_style_joinchat_invite_is_an_invite_not_a_username():
    """t.me/joinchat/HASH still circulates; read as @joinchat it would silently fetch a stranger."""
    assert [c.ref for c in parse_channels("channels:\n  - https://t.me/joinchat/AbCdEf123\n")] == ["+AbCdEf123"]


def test_an_internal_link_is_reduced_to_the_channel_id():
    """The /1 tail is a message number Telegram copied along -- not part of the channel."""
    assert [c.ref for c in parse_channels("channels:\n  - https://t.me/c/1949598843/1\n")] == ["c/1949598843"]


def test_a_bare_internal_id_needs_no_domain_at_all():
    """t.me has gone NXDOMAIN before; an id is what the agent actually uses, so it stands alone."""
    for spelling in ("c/1796089754", "1796089754", "-1001796089754", "c/1949598843/1/92775"):
        refs = [c.ref for c in parse_channels(f"channels:\n  - {spelling}\n")]
        assert refs == [f"c/{spelling.removeprefix('c/').removeprefix('-100').split('/')[0]}"], spelling


def test_a_public_group_is_accepted_as_handle_or_link():
    text = "channels:\n  - '@almatyriders'\n  - https://t.me/cyclingtourismalmaty\n"
    assert [c.ref for c in parse_channels(text)] == ["@almatyriders", "@cyclingtourismalmaty"]


def test_a_mapping_carries_the_hint_and_the_city():
    channel = parse_channels(
        """
        channels:
          - url: "@almatyriders"
            hint: "a club chat"
            city: Almaty
        """
    )[0]
    assert (channel.ref, channel.hint, channel.city) == ("@almatyriders", "a club chat", "Almaty")


def test_a_disabled_channel_is_left_out():
    text = "channels:\n  - url: '@paused'\n    enabled: false\n  - url: '@stays'\n"
    assert [c.ref for c in parse_channels(text)] == ["@stays"]


def test_the_same_channel_written_twice_is_read_once():
    text = "channels:\n  - '@almatyriders'\n  - https://t.me/AlmatyRiders\n"
    assert len(parse_channels(text)) == 1


def test_malformed_entries_are_skipped_rather_than_raising():
    text = "channels:\n  - ''\n  - 42\n  - url: ''\n  - '@good_one'\n"
    assert [c.ref for c in parse_channels(text)] == ["@good_one"]


def test_an_empty_or_broken_file_yields_no_channels():
    assert parse_channels("") == []
    assert parse_channels("just a string") == []
    assert parse_channels("channels: not-a-list") == []


def test_a_plain_list_without_the_channels_key_still_reads():
    assert [c.ref for c in parse_channels("- '@almatyriders'\n- https://t.me/+abcDEF123\n")] == [
        "@almatyriders",
        "+abcDEF123",
    ]


def test_the_shipped_channels_file_parses_and_names_only_readable_channels():
    channels = parse_channels(Path("telegram_channels.yaml").read_text(encoding="utf-8"))
    assert channels, "the shipped file should carry at least one enabled channel"
    assert all(c.ref and " " not in c.ref for c in channels)
    assert all(c.ref.startswith(("+", "c/", "@")) for c in channels)
