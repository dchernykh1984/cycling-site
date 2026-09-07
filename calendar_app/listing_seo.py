"""Titles and descriptions for a filtered competition list.

The filtered list has always been server-rendered: `/calendar/list/?location=2` returns the matching
events as plain HTML. What it lacked was any sign of what it holds -- every filter combination
carried the same title ("Competition list") and the same site-wide description, so a search engine
had one indistinguishable page instead of one per city and per discipline. "Races in Almaty" is the
shape of the query people type, and this is what answers it.
"""

from collections import Counter

from django.utils.translation import gettext as _

#: Every discipline whose English name starts this way is a category's leftovers bin -- "Other
#: (Road Cycling)", "Other (Running)". They are useful when an organizer's own wording fits nothing
#: else, and useless as a landing page: nobody searches for "other road cycling". The English name
#: is the one the seed data set, so it is the stable side to match on; the test below pins every
#: bin the catalogue currently holds.
CATCH_ALL_DISCIPLINE_PREFIX = "Other ("


def _names(model, ids, limit=3):
    if not ids:
        return []
    rows = list(model.objects.filter(pk__in=list(ids)[:limit]))
    return [row.name for row in rows]


def describe_filters(*, locations, disciplines, event_types, count, date_from=None, date_to=None):
    """A title and a description for the filters in force, or empty strings when there are none.

    Empty is deliberate: an unfiltered list has nothing of its own to say, and inventing a
    description for it would put the same words on it as on the site's other pages.
    """
    from calendar_app.models import Discipline, EventType
    from locations.models import Location

    places = _names(Location, locations)
    kinds = _names(Discipline, disciplines)
    types = _names(EventType, event_types)

    subject = ", ".join(kinds) if kinds else (", ".join(types) if types else _("Competitions"))
    title = subject
    if places:
        title = _("%(subject)s in %(place)s") % {"subject": subject, "place": ", ".join(places)}

    if not (places or kinds or types):
        return "", ""

    parts = [_("%(count)s events in the calendar.") % {"count": count}]
    if date_from and date_to:
        parts.append(_("From %(start)s to %(end)s.") % {"start": date_from, "end": date_to})
    parts.append(_("Dates, start points and results on the Universal Bicycle Team calendar."))
    return title, " ".join([f"{title}.", *parts])


def _by_weight(queryset, counts, limit):
    """The places holding the most races first, so a limit keeps the ones worth a page.

    Tree order decided this before, which on a calendar of two hundred towns meant the block under
    the calendar was filled by whichever region happens to sit first in the tree while Astana fell
    off the end.
    """
    return sorted(queryset, key=lambda node: (-counts.get(node.path, 0), node.name or ""))[:limit]


def landing_filters(limit_places=60, limit_kinds=40, limit_regions=30):
    """The filtered lists worth offering as pages of their own: regions, cities, disciplines.

    A city with no events is not a page about anything, so only places and disciplines that
    actually hold competitions are listed. Cities rather than the whole tree: "competitions in
    Almaty" is the query people type, "competitions in Kazakhstan" is what the calendar already is.

    Regions earn their own row because a village is not a search term. A start at Kyrbaltabay is
    invisible to anyone typing "races near Almaty", while the region page gathers that village
    together with Talgar, Yesik and Kaskelen into one page that answers the question actually
    asked. The list filter walks a node's descendants, so a region page needs no new plumbing.
    """
    from django.db.models import Count, Q
    from django.utils import timezone

    from locations.models import Location

    from .models import Competition, Discipline

    # Only what the page behind the link will actually show. The list starts at today, so a town
    # whose races are all in the past leads to an empty page -- and five of the six facets sampled
    # on production did exactly that, advertised in the sitemap and linked under the calendar.
    # One reading of the clock for the whole call: two would let a run that straddles midnight
    # count a race as ahead for the cities and behind for the disciplines.
    today = timezone.localdate()
    published = Competition.objects.filter(
        status=Competition.Status.APPROVED,
        is_hidden=False,
        is_deleted=False,
        date_start__gte=today,
    )
    # A venue sits at depth 4; its city is the first three path steps and its region the first two.
    # Counting the paths here rather than asking the database per node keeps this to one query and
    # gives the ordering below something to sort on.
    step = Location.steplen
    city_paths = list(published.filter(location__isnull=False).values_list("location__path", flat=True))
    city_counts = Counter(path[: step * 3] for path in city_paths if len(path) >= step * 3)
    region_counts = Counter(key[: step * 2] for key, races in city_counts.items() for _ in range(races))
    city_keys = set(city_counts)
    # The catch-all city ("Other city") is a bucket for events whose town nobody wrote down, not a
    # place anybody searches for. It is hidden in the tree for exactly that reason, and hidden nodes
    # have no business being offered as a page of their own.
    places = _by_weight(
        Location.objects.filter(depth=3, path__in=city_keys, is_deleted=False, is_hidden=False),
        city_counts,
        limit_places,
    )
    kinds = list(
        Discipline.objects.exclude(name_en__startswith=CATCH_ALL_DISCIPLINE_PREFIX)
        .annotate(
            events=Count(
                "competitions",
                filter=Q(
                    competitions__status=Competition.Status.APPROVED,
                    competitions__is_hidden=False,
                    competitions__is_deleted=False,
                    competitions__date_start__gte=today,
                ),
            )
        )
        .filter(events__gt=0)
        .order_by("-events", "pk")[:limit_kinds]
    )
    regions = _by_weight(
        Location.objects.filter(depth=2, path__in=set(region_counts), is_deleted=False, is_hidden=False),
        region_counts,
        limit_regions,
    )
    return regions, places, kinds
