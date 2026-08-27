"""Structured data for a competition page.

A search engine reading an event page has no way to tell a date from a phone number in prose. This
emits schema.org/SportsEvent, which is the vocabulary that feeds the event rich results -- the
listing that shows a date and a place under the link. We hold every field it wants already,
including the venue's exact coordinates.
"""

import json

from django.utils.html import escape


def sports_event(competition, base_url: str) -> str:
    """The JSON-LD body for ``competition``, ready to drop inside a script tag."""
    data: dict = {
        "@context": "https://schema.org",
        "@type": "SportsEvent",
        "name": competition.title,
        "startDate": competition.date_start.isoformat(),
        "url": f"{base_url}{competition.get_absolute_url()}",
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        # An event that has been and gone is not "scheduled" any more, but schema.org has no
        # "finished" status: the vocabulary only marks what went wrong (cancelled, postponed,
        # moved online). A past event simply keeps the default, and its date says the rest.
        "eventStatus": "https://schema.org/EventScheduled",
    }
    if competition.date_end and competition.date_end != competition.date_start:
        data["endDate"] = competition.date_end.isoformat()

    description = competition.search_summary()
    if description:
        data["description"] = description

    disciplines = [d.name for d in competition.disciplines.all()]
    if disciplines:
        # One name reads better than a list of one, and consumers accept either shape.
        data["sport"] = disciplines[0] if len(disciplines) == 1 else disciplines

    location = competition.location
    if location is not None:
        place: dict = {"@type": "Place", "name": location.name}
        address = [node.name for node in location.get_ancestors() if node.name]
        if address:
            place["address"] = {
                "@type": "PostalAddress",
                "addressLocality": address[-1],
                "addressCountry": address[0],
            }
        if location.lat is not None and location.lng is not None:
            place["geo"] = {
                "@type": "GeoCoordinates",
                "latitude": float(location.lat),
                "longitude": float(location.lng),
            }
        data["location"] = place

    if competition.url_registration:
        data["offers"] = {
            "@type": "Offer",
            "url": competition.url_registration,
            "availability": "https://schema.org/InStock",
        }

    # escape() keeps a "</script>" that reached a title from ending the block early.
    return escape(json.dumps(data, ensure_ascii=False))
