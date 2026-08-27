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
