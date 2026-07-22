"""Placing a candidate: reuse a known city, or propose the missing geography for review."""

from agent.locations import flatten_cities
from agent.models import Candidate
from agent.run import _resolve_location


def _tree():
    return [
        {
            "id": 1,
            "name": {"ru": "Kazakhstan-ru", "kk": "", "en": "Kazakhstan"},
            "children": [
                {
                    "id": 2,
                    "name": {"ru": "Almaty-region", "kk": "", "en": ""},
                    "children": [{"id": 3, "name": {"ru": "Almaty", "kk": "", "en": ""}, "children": []}],
                },
                {"id": 4, "name": {"ru": "drugoy-region", "kk": "", "en": "Other region"}, "children": []},
            ],
        },
        {
            "id": 5,
            "name": {"ru": "drugaya-strana", "kk": "", "en": "Other country"},
            "children": [{"id": 6, "name": {"ru": "x", "kk": "", "en": "Other region"}, "children": []}],
        },
    ]


class _FakeClient:
    """Records what the agent would have posted, handing back predictable ids."""

    def __init__(self):
        self.places: list[tuple[int, str]] = []
        self.venues: list[tuple[int, str]] = []
        self.fallbacks: list[int] = []
        self._next_id = 100

    def propose_place(self, parent_id, name):
        self._next_id += 1
        self.places.append((parent_id, name))
        return self._next_id

    def propose_venue(self, city_id, name, name_kk="", name_en="", lat=None, lng=None):
        self.venues.append((city_id, name))
        return 555

    def fallback_venue(self, city_id):
        self.fallbacks.append(city_id)
        return 999


def _resolve(candidate, tree=None):
    client, tree = _FakeClient(), tree if tree is not None else _tree()
    return client, _resolve_location(client, tree, flatten_cities(tree), candidate)


def _candidate(**kwargs):
    return Candidate(title="Race", date_start="2026-08-01", **kwargs)


def test_known_city_with_a_venue_proposes_only_the_venue():
    client, location_id = _resolve(_candidate(country="Kazakhstan", city="Almaty", venue="Medeu"))
    assert location_id == 555
    assert client.venues == [(3, "Medeu")]
    assert client.places == []


def test_known_city_without_a_venue_uses_the_city_fallback():
    client, location_id = _resolve(_candidate(city="Almaty"))
    assert location_id == 999
    assert client.fallbacks == [3]
    assert client.places == []


def test_unknown_city_in_a_known_region_is_proposed_under_it():
    client, location_id = _resolve(_candidate(country="Kazakhstan", region="Almaty-region", city="Talgar"))
    assert client.places == [(2, "Talgar")]  # the region already exists, only the city is new
    assert client.fallbacks == [101]
    assert location_id == 999


def test_unknown_region_is_proposed_before_the_city():
    client, _ = _resolve(_candidate(country="Kazakhstan", region="Zhetysu", city="Taldykorgan"))
    assert client.places == [(1, "Zhetysu"), (101, "Taldykorgan")]


def test_city_without_a_region_goes_under_the_catch_all_region():
    client, _ = _resolve(_candidate(country="Kazakhstan", city="Esik"))
    assert client.places == [(4, "Esik")]


def test_unknown_country_lands_under_the_catch_all_country():
    # Countries are admin-only, so the agent must never invent a root for one it does not know.
    client, _ = _resolve(_candidate(country="Iceland", city="Reykjavik"))
    assert client.places == [(6, "Reykjavik")]


def test_candidate_without_a_city_gets_no_location():
    client, location_id = _resolve(_candidate(country="Kazakhstan", venue="Somewhere"))
    assert location_id is None
    assert client.places == [] and client.venues == [] and client.fallbacks == []


def test_second_candidate_in_the_run_reuses_the_city_just_proposed():
    client, tree = _FakeClient(), _tree()
    cities = flatten_cities(tree)
    first = _candidate(country="Kazakhstan", region="Almaty-region", city="Talgar")
    second = _candidate(country="Kazakhstan", region="Almaty-region", city="Talgar", venue="Start")
    _resolve_location(client, tree, cities, first)
    _resolve_location(client, tree, cities, second)
    assert client.places == [(2, "Talgar")]  # proposed once, then reused from the in-memory index
    assert client.venues == [(101, "Start")]
