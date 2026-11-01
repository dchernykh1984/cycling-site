"""Structured data for a competition page.

A search engine reading an event page has no way to tell a date from a phone number in prose. This
emits schema.org/SportsEvent, which is the vocabulary that feeds the event rich results -- the
listing that shows a date and a place under the link. We hold every field it wants already,
including the venue's exact coordinates.
"""

from urllib.parse import urljoin

from django.urls import reverse

from cycling_site.jsonld import dumps
from locations.maps import start_point
from locations.models import Level


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
    # A one-day race ends the day it starts: search engines ask every event for its end.
    data["endDate"] = (competition.date_end or competition.date_start).isoformat()

    # The event's own preview picture, when it has one and its file is there: the site's mark is not a
    # picture of the event.
    image = competition.preview_image
    if image and image.storage.exists(image.name):
        data["image"] = [urljoin(base_url, image.url)]

    description = competition.search_summary()
    if description:
        data["description"] = description

    disciplines = [d.name for d in competition.disciplines.all()]
    if disciplines:
        # One name reads better than a list of one, and consumers accept either shape.
        data["sport"] = disciplines[0] if len(disciplines) == 1 else disciplines

    # Named only by what is known: a hidden stand-in drops out (Competition.place_name), the place is
    # called after the deepest level left, and only a venue's own point is a start to send.
    named = {level: name for level in Level if (name := competition.place_name(level))}
    if named:
        place: dict = {"@type": "Place", "name": named[max(named)]}
        postal = {
            key: named[level]
            for key, level in (
                ("addressCountry", Level.COUNTRY),
                ("addressRegion", Level.REGION),
                ("addressLocality", Level.CITY),
            )
            if level in named
        }
        if postal:
            place["address"] = {"@type": "PostalAddress", **postal}
        point = start_point(competition.location)
        if point is not None:
            place["geo"] = {"@type": "GeoCoordinates", "latitude": float(point[0]), "longitude": float(point[1])}
        data["location"] = place

    # Registration run on this site has no URL field: the page that takes the entry is the offer.
    # It wins over an external link the same way it does in the events list.
    if competition.is_registration_open():
        offer_url = f"{base_url}{reverse('registrations:register', args=[competition.pk])}"
    else:
        offer_url = competition.url_registration
    if offer_url:
        data["offers"] = {
            "@type": "Offer",
            "url": offer_url,
            "availability": "https://schema.org/InStock",
        }

    # dumps() keeps a "</script>" that reached a title from ending the block early, and the JSON valid.
    return dumps(data)
