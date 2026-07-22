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


def _hint_matches(hint: str, names: set[str]) -> bool:
    """Whether a free-text region/country hint plausibly names one of ``names``.

    Sources abbreviate ("Almaty obl.") and translate, so an exact comparison would reject good
    matches; a shared five-character opening or one name containing the other keeps those while
    still telling Chelyabinsk Oblast apart from Moscow Oblast.
    """
    target = normalize_name(hint)
    if not target:
        return True
    for name in names:
        if not name:
            continue
        if target == name or target in name or name in target:
            return True
        if len(target) >= 5 and len(name) >= 5 and target[:5] == name[:5]:
            return True
    return False


def city_matches(cities: list[dict], city: str, region: str = "", country: str = "") -> list[dict]:
    """Every city record matching the name, narrowed by region/country when that helps.

    Region/country only disambiguate when several cities share the name -- they never override an
    otherwise-unique match, so a slightly-off region name cannot break a good one.
    """
    target = normalize_name(city)
    if not target:
        return []
    matches = [c for c in cities if target in c["names"]]
    # Region and country are filters, not tie-breakers. A unique namesake in the wrong oblast used
    # to be accepted silently, which files a race hundreds of kilometres from where it is held --
    # far worse than proposing a second city for a human to look at. The comparison is loose enough
    # to survive the wording sources actually use ("Almaty obl." vs "Almaty Region").
    for hint, key in ((region, "region_names"), (country, "country_names")):
        if hint:
            matches = [c for c in matches if _hint_matches(hint, c[key])]
    return matches


def match_city(cities: list[dict], city: str, region: str = "", country: str = "") -> int | None:
    """The id of the single city that matches, or None when it is absent or ambiguous."""
    matches = city_matches(cities, city, region, country)
    return matches[0]["id"] if len(matches) == 1 else None


def is_ambiguous_city(cities: list[dict], city: str, region: str = "", country: str = "") -> bool:
    """Whether the name matches several cities -- a case to leave alone rather than add another.

    ``match_city`` answers None both for "the site does not have it" and for "the site has several",
    and only the first of those is a reason to propose a new city. Proposing on the ambiguous one
    would add a third namesake, which then makes the next candidate ambiguous too.
    """
    return len(city_matches(cities, city, region, country)) > 1


# The tree's catch-all nodes, matched on their English name (this module must stay ASCII-only).
_OTHER_COUNTRY = "other country"

# Russian sources use names the tree does not carry -- "Kirgiziya" for Kyrgyzstan, "Belorussiya"
# for Belarus. Without this the country looks unknown, the race is filed under the catch-all and
# every town from that source is proposed in the wrong place, run after run. Keys and values are
# normalized names; the value is matched against the tree in any locale. Escaped rather than
# written out because this module must stay ASCII-only.
_COUNTRY_ALIASES = {
    "\u043a\u0438\u0440\u0433\u0438\u0437\u0438\u044f": "kyrgyzstan",
    "\u0431\u0435\u043b\u043e\u0440\u0443\u0441\u0441\u0438\u044f": "belarus",
    "\u043c\u043e\u043b\u0434\u043e\u0432\u0430": "moldova",
    "\u0433\u043e\u043b\u043b\u0430\u043d\u0434\u0438\u044f": "netherlands",
    "\u0441\u043e\u0435\u0434\u0438\u043d\u0435\u043d\u043d\u044b\u0435 "
    "\u0448\u0442\u0430\u0442\u044b": "united states",
    "\u0447\u0435\u0448\u0441\u043a\u0430\u044f "
    "\u0440\u0435\u0441\u043f\u0443\u0431\u043b\u0438\u043a\u0430": "czech republic",
    "turkiye": "turkey",
    "kyrgyz republic": "kyrgyzstan",
}


def _match_node(nodes: list[dict], name: str) -> dict | None:
    """The single node of ``nodes`` whose name matches in any locale, or None if absent/ambiguous."""
    target = normalize_name(name)
    if not target:
        return None
    matches = [n for n in nodes or [] if target in _names(n)]
    return matches[0] if len(matches) == 1 else None


def _catch_all(nodes: list[dict], marker: str) -> dict | None:
    for node in nodes or []:
        if marker in _names(node):
            return node
    return None


def match_country(tree: list[dict], country: str) -> dict | None:
    """The country node for this name; a named but unknown country falls back to the catch-all.

    Countries are admin-only, so the agent never creates one: an event in a country the site does
    not carry is filed under "Other country" and a human moves it later. An *unnamed* country is a
    different case and gets None -- guessing there would file a real region under the catch-all.
    """
    target = normalize_name(country)
    if not target:
        return None
    return (
        _match_node(tree, country)
        or _match_node(tree, _COUNTRY_ALIASES.get(target, ""))
        or _catch_all(tree, _OTHER_COUNTRY)
    )


def match_region(country: dict, region: str) -> dict | None:
    """The region node under ``country`` matching this name, or None when it is absent/ambiguous."""
    return _match_node((country or {}).get("children") or [], region)


def city_record(city_id: int, city: str, region: dict, country: dict) -> dict:
    """A freshly proposed city as a `flatten_cities` record, so the same run can reuse it."""
    return {
        "id": city_id,
        "names": {normalize_name(city)},
        "region_names": _names(region or {}),
        "country_names": _names(country or {}),
    }
