"""Titles and descriptions for a filtered competition list.

The filtered list has always been server-rendered: `/calendar/list/?location=2` returns the matching
events as plain HTML. What it lacked was any sign of what it holds -- every filter combination
carried the same title ("Competition list") and the same site-wide description, so a search engine
had one indistinguishable page instead of one per city and per discipline. "Races in Almaty" is the
shape of the query people type, and this is what answers it.
"""

from django.utils.translation import gettext as _


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


def landing_filters(limit_places=60, limit_kinds=40):
    """The filtered lists worth offering as pages of their own.

    A city with no events is not a page about anything, so only places and disciplines that
    actually hold competitions are listed. Cities rather than the whole tree: "competitions in
    Almaty" is the query people type, "competitions in Kazakhstan" is what the calendar already is.
    """
    from django.db.models import Count, Q

    from locations.models import Location

    from .models import Competition, Discipline

    published = Competition.objects.filter(status=Competition.Status.APPROVED, is_hidden=False, is_deleted=False)
    city_paths = published.filter(location__isnull=False).values_list("location__path", flat=True)
    # A venue sits at depth 4; its city is the first three path steps.
    step = Location.steplen
    city_keys = {path[: step * 3] for path in city_paths if len(path) >= step * 3}
    places = list(
        Location.objects.filter(depth=3, path__in=city_keys, is_deleted=False).order_by("path")[:limit_places]
    )
    kinds = list(
        Discipline.objects.annotate(
            events=Count(
                "competitions",
                filter=Q(
                    competitions__status=Competition.Status.APPROVED,
                    competitions__is_hidden=False,
                    competitions__is_deleted=False,
                ),
            )
        )
        .filter(events__gt=0)
        .order_by("-events", "pk")[:limit_kinds]
    )
    return places, kinds
