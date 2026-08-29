"""A public Telegram feed, as the model reads it.

The model is told to link the post an event was announced in. It could not: the feed was flattened
into text and the permalink Telegram puts on each post's date went out with the markup, so events
from these sources came out with no announcement link at all.
"""

from bs4 import BeautifulSoup

from agent.fetch import telegram_posts

FEED = """
<div class="tgme_widget_message" data-post="mystartkz/936">
  <a class="tgme_widget_message_date" href="https://t.me/mystartkz/936"><time>Aug 20</time></a>
  <div class="tgme_widget_message_text">JAZ RUN 2026, 16 September, Kulsary</div>
</div>
<div class="tgme_widget_message" data-post="mystartkz/937">
  <a class="tgme_widget_message_date" href="https://t.me/mystartkz/937"><time>Aug 21</time></a>
  <div class="tgme_widget_message_text">TEMIR MARATHON 2026</div>
</div>
"""


def _posts(html):
    return telegram_posts(BeautifulSoup(html, "html.parser"))


def test_each_post_is_headed_by_its_own_address():
    first, second = _posts(FEED)
    assert first.startswith("--- post https://t.me/mystartkz/936\n")
    assert "JAZ RUN 2026" in first
    assert second.startswith("--- post https://t.me/mystartkz/937\n")


def test_the_address_falls_back_to_the_link_on_the_date():
    """Telegram writes the id twice; a feed missing the attribute still has the dated permalink."""
    html = """
    <div class="tgme_widget_message">
      <a class="tgme_widget_message_date" href="https://t.me/roadcyclingkz/407"></a>
      <div class="tgme_widget_message_text">Race on Sunday</div>
    </div>
    """
    assert _posts(html) == ["--- post https://t.me/roadcyclingkz/407\nRace on Sunday"]


def test_a_post_with_no_address_is_still_read():
    """Losing the event would cost more than losing its link."""
    html = '<div class="tgme_widget_message"><div class="tgme_widget_message_text">Race on Sunday</div></div>'
    assert _posts(html) == ["Race on Sunday"]


def test_a_message_without_text_is_skipped():
    """A photo with no caption announces nothing the model can read."""
    html = '<div class="tgme_widget_message" data-post="c/1/2"><div class="tgme_widget_message_photo"></div></div>'
    assert _posts(html) == []


def test_posts_keep_the_order_the_channel_published_them_in():
    assert [p.splitlines()[0] for p in _posts(FEED)] == [
        "--- post https://t.me/mystartkz/936",
        "--- post https://t.me/mystartkz/937",
    ]
