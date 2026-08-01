"""Placing a proposed event on the site's location tree: shared by every agent that proposes one.

An event is only useful on a calendar if it lands somewhere -- a start venue when the announcement
names one, the city's catch-all otherwise -- and a city the tree does not carry yet is proposed for
review rather than dropped. Both the web agent and the Instagram agent place events the same way, so
this lives apart from either runner.
"""

from __future__ import annotations

from agent import locations
from agent.models import Candidate


def propose_city(client, tree: list, cities: list, candidate: Candidate, created: list | None = None) -> int | None:
    """Propose the candidate's city, and its region when that is new too; None if not possible.

    Both land pending: the agent may use them straight away, everyone else sees them once a reviewer
    approves. Countries are admin-only, so an event in a country the site does not carry goes under
    the tree's catch-all country instead of inventing a root.
    """
    # A name that is only punctuation ("-", "()") survives the "not empty" test but normalizes to
    # nothing, so every guard below would pass it through and post it verbatim as a place. Treat a
    # region or city with no real content as absent.
    if not locations.has_real_name(candidate.city) or not locations.has_real_name(candidate.region):
        return None
    if locations.is_ambiguous_city(cities, candidate.city, candidate.region, candidate.country):
        return None
    # The model is told to give a real place and a first-level region, but nothing stops it echoing
    # the site's own placeholder or handing back a district; either one would become a permanent
    # node here, so refuse and let a reviewer place the event instead.
    if locations.is_placeholder_name(
        candidate.city, candidate.city_kk, candidate.city_en, candidate.region, candidate.region_kk, candidate.region_en
    ):
        return None
    country = locations.match_country(tree, candidate.country)
    if country is None or locations.is_catch_all_country(country):
        # Without a country we cannot place anything. And when the name resolved to the tree's
        # "Other country" bucket, the site simply does not carry that country -- hanging a real
        # region under that bucket is structurally meaningless, so leave the event unplaced for a
        # human to add the country and place it. (A content-free region was already refused above.)
        return None
    region = locations.match_region(country, candidate.region)
    if region is None:
        if locations.looks_like_district(candidate.region):
            return None
        region_id = client.propose_place(country["id"], candidate.region, candidate.region_kk, candidate.region_en)
        region = {
            "id": region_id,
            "name": {"ru": candidate.region, "kk": candidate.region_kk, "en": candidate.region_en},
        }
        if created is not None:
            created.append(f"region {candidate.region!r} (#{region_id})")
        country.setdefault("children", []).append(region)
    city_id = client.propose_place(region["id"], candidate.city, candidate.city_kk, candidate.city_en)
    if created is not None:
        created.append(f"city {candidate.city!r} (#{city_id})")
    # Keep the flat index in step so a later candidate in the same run reuses the new city.
    cities.append(
        locations.city_record(city_id, (candidate.city, candidate.city_kk, candidate.city_en), region, country)
    )
    return city_id


def resolve_location(client, tree: list, cities: list, candidate: Candidate, created: list | None = None) -> int | None:
    """Concrete start venue when the city is known and named; else the city's catch-all.

    A city the tree does not have yet is proposed rather than skipped, so the event is placed from
    the start and the reviewer only has to confirm the geography.
    """
    city_id = locations.match_city(cities, candidate.city, candidate.region, candidate.country)
    if city_id is None:
        city_id = propose_city(client, tree, cities, candidate, created)
    if city_id is None:
        # Nothing to hang the event on: an unnamed or ambiguous city, or no country/region to
        # place it under. The event is still worth proposing -- the guidance asks the model to
        # repeat the place in the description, so a reviewer can set the location by hand.
        return None
    if candidate.venue:
        return client.propose_venue(
            city_id, candidate.venue, candidate.venue_kk, candidate.venue_en, candidate.lat, candidate.lng
        )
    return client.fallback_venue(city_id)
