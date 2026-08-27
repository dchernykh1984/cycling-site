"""News as a feed.

An RSS reader, an aggregator or a Telegram bot can follow the site without anyone having to visit
it, and a feed is one of the few things a crawler will come back to on its own.
"""

from django.contrib.syndication.views import Feed
from django.urls import reverse
from django.utils.feedgenerator import Atom1Feed
from django.utils.translation import gettext_lazy as _

from cycling_site.summaries import summarize

from .models import NewsArticle


class NewsFeed(Feed):
    title = _("Universal Bicycle Team news")
    description = _("Announcements, results and stories from the Universal Bicycle Team calendar.")
    #: How many items one fetch carries. A reader wants the recent ones, not the archive.
    item_count = 20

    def link(self):
        return reverse("news_index")

    def items(self):
        return NewsArticle.objects.filter(is_hidden=False, is_deleted=False).order_by("-published_at")[
            : self.item_count
        ]

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return item.intro or summarize(item.body)

    def item_link(self, item):
        return item.get_absolute_url()

    def item_pubdate(self, item):
        return item.published_at


class NewsAtomFeed(NewsFeed):
    """The same items in Atom, for readers that prefer it."""

    feed_type = Atom1Feed
    subtitle = NewsFeed.description
