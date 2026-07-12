"""Pure helpers to match an LLM-named city to a site location id (no I/O, unit-tested).

The site's locations are a tree country -> region -> city -> venue. The LLM gives us free-text
country/region/city names; here we turn the fetched tree into flat city records and find the one
city that unambiguously matches, refusing to guess when the match is ambiguous.
"""

from __future__ import annotations

import re

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def normalize_name(value: str) -> str:
    """Lower-case, drop punctuation and collapse whitespace, for locale-insensitive comparison."""
    norm = _PUNCT.sub(" ", (value or "").lower())
    return _WS.sub(" ", norm).strip()


def _names(node: dict) -> set[str]:
    """Normalized name of a tree node across all locales (accepts a LocalizedStr dict or a string)."""
    name = node.get("name")
    if isinstance(name, dict):
        values = [name.get("ru"), name.get("kk"), name.get("en")]
    else:
        values = [name]
    return {normalize_name(v) for v in values if v}


def flatten_cities(tree: list[dict]) -> list[dict]:
    """City records (the depth-3 nodes) carrying their own, region and country normalized names."""
    cities: list[dict] = []
    for country in tree or []:
        country_names = _names(country)
        for region in country.get("children") or []:
            region_names = _names(region)
            for city in region.get("children") or []:
                if city.get("id") is None:
                    continue
                cities.append(
                    {
                        "id": city["id"],
                        "names": _names(city),
                        "region_names": region_names,
                        "country_names": country_names,
                    }
                )
    return cities


def match_city(cities: list[dict], city: str, region: str = "", country: str = "") -> int | None:
    """Return the id of the single city that matches, or None when it is absent or ambiguous.

    Region/country are used only to disambiguate when several cities share the name -- never to
    override an otherwise-unique match, so a slightly-off region name cannot break a good match.
    """
    target = normalize_name(city)
    if not target:
        return None
    matches = [c for c in cities if target in c["names"]]
    if len(matches) > 1 and region:
        narrowed = [c for c in matches if normalize_name(region) in c["region_names"]]
        if narrowed:
            matches = narrowed
    if len(matches) > 1 and country:
        narrowed = [c for c in matches if normalize_name(country) in c["country_names"]]
        if narrowed:
            matches = narrowed
    return matches[0]["id"] if len(matches) == 1 else None
