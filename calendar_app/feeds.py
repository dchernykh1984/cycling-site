"""Subscription feeds for the calendar, and one event's calendar file.

A rider who subscribes once keeps seeing our events in their own phone calendar, and a search
engine that finds the feed has one more, always-fresh path into the site. The ICS feed answers
the same filters as the list view, so whatever selection someone built in the browser can be
subscribed to as it stands. An event's page offers the same entry for that event alone, to add
once to whatever calendar the reader uses (issue #398).
"""

import datetime

from django.contrib.syndication.views import Feed
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import patch_cache_control
from django.utils.feedgenerator import Atom1Feed
from django.utils.translation import gettext_lazy as _
from django.views.generic import View

from locations.maps import start_point

from .models import Competition, usual_event_type_id
from .views import _apply_id_filters, _location_descendant_pks
from .visibility import can_open

#: How far back a subscription still shows events. A calendar that drops an event the morning
#: after it finished is confusing; a month of history is enough to look up last weekend's race.
PAST_WINDOW = datetime.timedelta(days=30)

#: Upper bound on one feed, so a crawler or a broken client cannot ask for the whole archive.
MAX_EVENTS = 1000


def filtered_competitions(request: HttpRequest) -> list[Competition]:
    """Public events matching the filters in the query string, nearest first."""
    qs = (
        # Read by calendar apps with no session, so an invite-only event never rides along.
        Competition.objects.filter(
            status=Competition.Status.APPROVED, is_deleted=False, is_hidden=False, invite_only=False
        )
        # The venue's fallback mark decides whether its point goes out (start_point): one join,
        # not a query per event.
        .select_related("location", "location__fallback_identity")
        .prefetch_related("event_types", "disciplines__category")
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


def _event_lines(
    competition: Competition, base_url: str, now: datetime.datetime, usual_type_id: int | None
) -> list[str]:
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
    # Only a venue's own point: a city's centre in a calendar reads as the start line (locations.maps).
    point = start_point(competition.location)
    if point is not None:
        lines.append(f"GEO:{point[0]:.6f};{point[1]:.6f}")
    lines.append(f"DESCRIPTION:{_escape(competition.search_summary(usual_type_id))}")
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
    usual_type_id = usual_event_type_id()
    for competition in competitions:
        lines.extend(_event_lines(competition, base_url, now, usual_type_id))
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def site_base_url(request: HttpRequest) -> str:
    """The site's address that the calendar's links start with, without a trailing slash."""
    from django.conf import settings

    return getattr(settings, "SITE_BASE_URL", "").rstrip("/") or request.build_absolute_uri("/").rstrip("/")


def calendar_response(body: str, filename: str) -> HttpResponse:
    response = HttpResponse(body, content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


class CompetitionICSView(View):
    """`/calendar/calendar.ics`, with the same query string the list view takes."""

    def get(self, request: HttpRequest) -> HttpResponse:
        body = build_calendar(filtered_competitions(request), site_base_url(request))
        return calendar_response(body, "universalbicycle.ics")


class CompetitionEventICSView(View):
    """`/calendar/<id>/event.ics`: one event, for whoever may open its page (issue #398)."""

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        competition = get_object_or_404(
            Competition.objects.select_related("location", "location__fallback_identity"), pk=pk
        )
        if not can_open(request.user, competition):
            raise Http404
        response = calendar_response(build_calendar([competition], site_base_url(request)), f"event-{pk}.ics")
        # The page is what a search engine should find, not a copy of it in another format.
        response["X-Robots-Tag"] = "noindex"
        # Who gets it depends on who asks (a hidden or invite-only event): no shared cache keeps a copy.
        patch_cache_control(response, private=True)
        return response


class NewCompetitionsFeed(Feed):
    """Events as they are approved -- what changed since the reader last looked.

    Ordered by approval rather than by date, because that is the question a subscriber has:
    not "what is on next month" (the ICS feed answers that) but "what has been added".
    """

    title = _("New events")
    description = _("Events recently added to the Universal Bicycle Team calendar.")
    item_count = 30

    def link(self):
        return reverse("calendar_list")

    def items(self):
        items = list(
            Competition.objects.filter(
                status=Competition.Status.APPROVED,
                is_deleted=False,
                is_hidden=False,
                invite_only=False,
                # Postgres sorts NULLs first in a descending order, so an event approved before
                # the timestamp existed would head the feed of what is new.
                approved_at__isnull=False,
            )
            .select_related("location")
            .prefetch_related("event_types", "disciplines__category")
            .order_by("-approved_at", "-pk")[: self.item_count]
        )
        # Each description leaves the usual type unsaid: looked up once for the feed, not once an item
        usual = usual_event_type_id()
        for item in items:
            item.usual_type_id = usual
        return items

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return item.search_summary(item.usual_type_id)

    def item_link(self, item):
        return item.get_absolute_url()

    def item_pubdate(self, item):
        return item.approved_at


class NewCompetitionsAtomFeed(NewCompetitionsFeed):
    feed_type = Atom1Feed
    subtitle = NewCompetitionsFeed.description
