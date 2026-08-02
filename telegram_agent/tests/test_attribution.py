"""How an event says where it was announced, without handing out a way in."""

from agent.models import Candidate
from telegram_agent.attribution import credit_source, source_label


def _candidate(**kwargs):
    defaults = {"title": "Saturday Ride", "date_start": "2026-08-08"}
    return Candidate(**{**defaults, **kwargs})


def test_a_public_group_is_credited_by_its_searchable_handle():
    assert source_label("@almatyriders", "Almaty Riders") == "tg: @almatyriders"


def test_a_private_channel_is_credited_by_its_display_name_alone():
    """The name invites nobody in; an id or an invite hash would."""
    assert source_label("c/1796089754", "Velosreda s Alatau Racing") == "Velosreda s Alatau Racing"
    assert source_label("+AbCdEfGhIjKlMnOp", "Velosreda s Alatau Racing") == "Velosreda s Alatau Racing"


def test_a_private_channel_with_no_name_is_credited_as_nothing():
    """Better no credit than the invite or the id."""
    assert source_label("c/1796089754", "") == ""
    assert credit_source(_candidate(description="<p>Ride.</p>"), "").description == "<p>Ride.</p>"


def test_a_link_inside_a_channel_name_does_not_reach_the_credit():
    assert source_label("c/1796089754", "Ride club (t.me/+secret)") == "Ride club ("


def test_the_credit_is_appended_to_every_locale():
    credited = credit_source(
        _candidate(description="<p>Ride.</p>", description_kk="<p>K.</p>", description_en="<p>E.</p>"),
        "tg: @almatyriders",
    )
    assert credited.description.endswith(": tg: @almatyriders</p>")
    assert credited.description_kk.endswith(": tg: @almatyriders</p>")
    assert credited.description_en.endswith("<p>Announcement source: tg: @almatyriders</p>")
    assert credited.description.startswith("<p>Ride.</p>\n")


def test_an_empty_description_becomes_just_the_credit():
    assert credit_source(_candidate(), "tg: @almatyriders").description_en == (
        "<p>Announcement source: tg: @almatyriders</p>"
    )
