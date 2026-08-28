"""Which address may stand in for an event's announcement.

When the model finds no link of its own, the address the text was read from is the obvious
stand-in -- and for a forum index or a channel feed it is the wrong one. Real events carried
`https://forum.velomania.ru/` and `https://t.me/s/mystartkz` as their announcement link, both of
which drop the reader into a list of dozens of posts.
"""

import pytest

from agent.links import announces_one_event


@pytest.mark.parametrize(
    "url",
    [
        "https://forum.velomania.ru/showthread.php?t=1234567",
        "https://velosport.kg/calendar/3-apricot-gravel-mtb-marathon-race.html",
        "https://athletex.kz/competitions/AlpineRace2026",
        "https://t.me/mystartkz/951",  # one post
        "https://t.me/roadcyclingkz/407",
        "https://t.me/c/1949598843/93485",  # one post in a private chat
        "https://www.themountainraces.cc/hellenic-mountain-race",
    ],
)
def test_a_page_about_one_event_may_stand_in(url):
    assert announces_one_event(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://forum.velomania.ru/",
        "https://forum.velomania.ru",
        "https://t.me/s/mystartkz",
        "https://t.me/s/mystartkz/",
        "https://t.me/mystartkz",  # the channel itself, not a post in it
        "https://www.granfondo.ru/",
        "http://bike-events.ru",
    ],
)
def test_a_listing_may_not(url):
    assert not announces_one_event(url)


@pytest.mark.parametrize("url", ["", "   ", "not a url", "mtproto:c/1949598843", "ftp://example.com/x"])
def test_anything_that_is_not_a_web_address_may_not(url):
    """The Telegram agent's sources are addressed by a pseudo-scheme nothing can open."""
    assert not announces_one_event(url)
