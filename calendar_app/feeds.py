"""Subscription feeds for the calendar.

A rider who subscribes once keeps seeing our events in their own phone calendar, and a search
engine that finds the feed has one more, always-fresh path into the site. The ICS feed answers
the same filters as the list view, so whatever selection someone built in the browser can be
subscribed to as it stands.
"""

import datetime

from django.contrib.syndication.views import Feed
from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.feedgenerator import Atom1Feed
from django.utils.translation import gettext_lazy as _
from django.views.generic import View

from .models import Competition
from .views import _apply_id_filters, _location_descendant_pks

#: How far back a subscription still shows events. A calendar that drops an event the morning
#: after it finished is confusing; a month of history is enough to look up last weekend's race.
PAST_WINDOW = datetime.timedelta(days=30)

#: Upper bound on one feed, so a crawler or a broken client cannot ask for the whole archive.
MAX_EVENTS = 1000


def filtered_competitions(request: HttpRequest) -> list[Competition]:
    """Public events matching the filters in the query string, nearest first."""
    qs = (
        Competition.objects.filter(status=Competition.Status.APPROVED, is_deleted=False, is_hidden=False)
        .select_related("location")
        .prefetch_related("disciplines")
    )
    qs = _apply_id_filters(
        qs,
        request.GET.getlist("event_type"),
        request.GET.getlist("discipline"),
        request.GET.getlist("discipline_category"),
    )
    location_ids = request.GET.getlist("location")
    if location_ids:
        qs = qs.filter(location_id__in=_location_descendant_pks(location_ids))
    qs = qs.filter(date_start__gte=timezone.localdate() - PAST_WINDOW)
    return list(qs.order_by("date_start", "pk")[:MAX_EVENTS])


def _escape(value: str) -> str:
    """RFC 5545 text escaping: backslash first, then the separators, then newlines."""
    out = value.replace("\\", "\\\\")
    for char in (";", ","):
        out = out.replace(char, "\\" + char)
    return out.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")


def _fold(line: str) -> str:
    """Wrap at 75 octets, continuing with a leading space, as the format requires.

    Counted in bytes rather than characters: an event named in Cyrillic is two bytes per letter,
    and a client that reads the length as octets sees a broken line otherwise. A character is
    never split across the fold.
    """
    out: list[str] = []
    current = ""
    budget = 75
    for char in line:
        size = len(char.encode())
        if budget - size < 0:
            out.append(current)
            current = char
            budget = 74 - size  # the continuation line starts with a space
        else:
            current += char
            budget -= size
    out.append(current)
    return "\r\n ".join(out)


def _stamp(moment: datetime.datetime) -> str:
    return moment.astimezone(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")


def _event_lines(competition: Competition, base_url: str, now: datetime.datetime) -> list[str]:
    # An all-day VEVENT ends on the day *after* the last one, and a single-day event with no end
    # date still needs a DTEND, or clients disagree about how long it lasts.
    last_day = competition.date_end or competition.date_start
    if last_day < competition.date_start:
        last_day = competition.date_start
    url = base_url + reverse("competition_detail", kwargs={"pk": competition.pk})
    lines = [
        "BEGIN:VEVENT",
        f"UID:competition-{competition.pk}@universalbicycle.team",
        f"DTSTAMP:{_stamp(now)}",
        f"DTSTART;VALUE=DATE:{competition.date_start:%Y%m%d}",
        f"DTEND;VALUE=DATE:{last_day + datetime.timedelta(days=1):%Y%m%d}",
        f"SUMMARY:{_escape(competition.title)}",
        f"URL:{_escape(url)}",
    ]
    where = competition.location_label or competition.city_label
    if where:
        lines.append(f"LOCATION:{_escape(where)}")
    lines.append(f"DESCRIPTION:{_escape(competition.search_summary())}")
    lines.append("END:VEVENT")
    return lines


def build_calendar(competitions: list[Competition], base_url: str) -> str:
    now = timezone.now()
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Universal Bicycle Team//Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Universal Bicycle Team",
    ]
    for competition in competitions:
        lines.extend(_event_lines(competition, base_url, now))
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


class CompetitionICSView(View):
    """`/calendar/calendar.ics`, with the same query string the list view takes."""

    def get(self, request: HttpRequest) -> HttpResponse:
        from django.conf import settings

        base_url = getattr(settings, "SITE_BASE_URL", "").rstrip("/")
        if not base_url:
            base_url = request.build_absolute_uri("/").rstrip("/")
        body = build_calendar(filtered_competitions(request), base_url)
        response = HttpResponse(body, content_type="text/calendar; charset=utf-8")
        response["Content-Disposition"] = 'inline; filename="universalbicycle.ics"'
        return response


class NewCompetitionsFeed(Feed):
    """Events as they are approved -- what changed since the reader last looked.

    Ordered by approval rather than by date, because that is the question a subscriber has:
    not "what is on next month" (the ICS feed answers that) but "what has been added".
    """

    title = _("New competitions")
    description = _("Competitions recently added to the Universal Bicycle Team calendar.")
    item_count = 30

    def link(self):
        return reverse("calendar_list")

    def items(self):
        return (
            Competition.objects.filter(
                status=Competition.Status.APPROVED,
                is_deleted=False,
                is_hidden=False,
                # Postgres sorts NULLs first in a descending order, so an event approved before
                # the timestamp existed would head the feed of what is new.
                approved_at__isnull=False,
            )
            .select_related("location")
            .prefetch_related("disciplines")
            .order_by("-approved_at", "-pk")[: self.item_count]
        )

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return item.search_summary()

    def item_link(self, item):
        return item.get_absolute_url()

    def item_pubdate(self, item):
        return item.approved_at


class NewCompetitionsAtomFeed(NewCompetitionsFeed):
    feed_type = Atom1Feed
    subtitle = NewCompetitionsFeed.description
