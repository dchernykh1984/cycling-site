"""Finding the place the model named among the site's own places (issue #353).

The model names the start in words and the site's tree decides, with the import agents' matching:
one way of telling two spellings of a place apart for the whole site. The tree is the one the
event's page offers (``_get_locations_data``), so the chat never picks a place the page cannot show.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent import locations as agent_locations
from agent import venues as agent_venues
from locations.models import Level

Point = tuple[float, float]


@dataclass
class Place:
    """A venue of the site's, or a new venue to propose, or nothing with the city that was not found."""

    location: int | None = None
    new_venue: dict | None = None
    missing_city: str = ""


def tree(rows: list[dict]) -> list[dict]:
    """The page's flat list of places as the agents' tree of countries, regions, cities and venues."""
    by_path: dict[str, dict] = {}
    roots: list[dict] = []
    for row in sorted(rows, key=lambda r: r["path"]):
        node = {
            "id": row["pk"],
            "name": {"ru": row["name_ru"] or "", "kk": row["name_kk"] or "", "en": row["name_en"] or ""},
            "lat": row["lat"],
            "lng": row["lng"],
            "is_hidden": row["is_hidden"],
            "children": [],
        }
        by_path[row["path"]] = node
        if row["depth"] == Level.COUNTRY:
            roots.append(node)
            continue
        step = len(row["path"]) // row["depth"]
        parent = by_path.get(row["path"][:-step])
        if parent is not None:
            parent["children"].append(node)
    return roots


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def resolve(place: dict, rows: list[dict], point: Point | None) -> Place:
    """The venue ``place`` names, the city's own catch-all when it names no spot, or a new venue."""
    city_name = _text(place.get("city"))
    if not city_name:
        return Place()
    nodes = tree(rows)
    city_id = agent_locations.match_city(
        agent_locations.flatten_cities(nodes), city_name, _text(place.get("region")), _text(place.get("country"))
    )
    if city_id is None:
        return Place(missing_city=city_name)
    city = agent_venues.city_node(nodes, city_id) or {}
    venue = place.get("venue")
    names = {lang: _text(venue.get(lang)) for lang in ("ru", "kk", "en")} if isinstance(venue, dict) else {}
    if not any(names.values()):
        catch_all = next((child for child in city.get("children", []) if child["is_hidden"]), None)
        return Place(location=catch_all["id"]) if catch_all else Place()
    said = [name for name in names.values() if name]
    for node in city.get("children", []):
        if node["is_hidden"]:
            continue
        known_point = (node["lat"], node["lng"]) if node["lat"] is not None and node["lng"] is not None else None
        known_names = [name for name in node["name"].values() if name]
        if any(agent_venues.same_place(a, point, b, known_point) for a in said for b in known_names):
            return Place(location=node["id"])
    return Place(
        new_venue={
            "city": city_id,
            "name_ru": names["ru"] or names["en"] or names["kk"],
            "name_kk": names["kk"],
            "name_en": names["en"],
            "lat": point[0] if point else None,
            "lng": point[1] if point else None,
        }
    )
