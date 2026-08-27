"""The pager, read as a crawler reads it.

With only "previous" and "next" the competition list is a chain: reaching page 26 costs 25
requests, and a crawler that gives up early never sees the events at the end.

The list narrows to a 30-day window unless asked otherwise, so these tests pass an explicit range
-- otherwise most of the fixture would be filtered out before it ever reached the pager.
"""

import datetime
import re

from django.test import TestCase
from django.urls import reverse

from calendar_app.models import Competition

FIRST = datetime.date.today() + datetime.timedelta(days=5)
SPAN = {"date_from": FIRST.isoformat(), "date_to": (FIRST + datetime.timedelta(days=80)).isoformat()}


class NumberedPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for i in range(65):  # four pages at 20 per page
            Competition.objects.create(
                title_ru=f"Race {i}",
                date_start=FIRST + datetime.timedelta(days=i),
                status=Competition.Status.APPROVED,
            )

    def _html(self, **params):
        return self.client.get(reverse("calendar_list"), {**SPAN, **params}).content.decode()

    def _page_links(self, html):
        # &amp; in the markup, not &: the links are HTML-escaped.
        return sorted({int(n) for n in re.findall(r"(?:\?|&amp;|&)page=(\d+)", html)})

    def test_the_fixture_really_spans_several_pages(self):
        page = self.client.get(reverse("calendar_list"), SPAN).context["competitions"]
        self.assertGreaterEqual(page.paginator.num_pages, 4)

    def test_page_one_links_further_than_the_next_page(self):
        self.assertGreater(len(self._page_links(self._html())), 1)

    def test_the_last_page_is_reachable_from_the_first(self):
        html = self._html()
        last = self.client.get(reverse("calendar_list"), SPAN).context["competitions"].paginator.num_pages
        self.assertIn(last, self._page_links(html))

    def test_prev_and_next_are_marked_up(self):
        html = self._html(page=2)
        self.assertIn('rel="prev"', html)
        self.assertIn('rel="next"', html)

    def test_filters_survive_a_page_change(self):
        html = self._html(page=2, direction="1")
        links = re.findall(r'href="(\?[^"]*page=\d+[^"]*)"', html)
        self.assertTrue(links)
        self.assertTrue(all("direction=1" in link for link in links))
