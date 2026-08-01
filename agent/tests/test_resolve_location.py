"""Placing a candidate: reuse a known city, or propose the missing geography for review."""

from agent.locations import flatten_cities, match_city
from agent.models import Candidate
from agent.placing import resolve_location as _resolve_location


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
        self.locales: list[tuple] = []
        self._next_id = 100

    def propose_place(self, parent_id, name, name_kk="", name_en=""):
        self._next_id += 1
        self.places.append((parent_id, name))
        self.locales.append((name, name_kk, name_en))
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


def test_city_without_a_named_region_is_not_proposed():
    # The tree's catch-all regions are hidden, so the API never returns one to hang the city on.
    client, location_id = _resolve(_candidate(country="Kazakhstan", city="Esik"))
    assert location_id is None
    assert client.places == []


def test_city_without_a_named_country_is_not_proposed():
    # Falling back to the catch-all country here would file a real region under "Other country".
    client, location_id = _resolve(_candidate(region="Almaty-region", city="Esik"))
    assert location_id is None
    assert client.places == []


def test_unknown_country_leaves_the_event_unplaced():
    # A country the site does not carry resolves to the "Other country" bucket. Hanging a real
    # region under that bucket is meaningless, so nothing is proposed -- a human adds the country.
    client, location_id = _resolve(_candidate(country="Atlantis", region="Capital Region", city="Reykjavik"))
    assert location_id is None
    assert client.places == []


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


def _tree_with_twin_cities():
    tree = _tree()
    tree[0]["children"].append(
        {
            "id": 7,
            "name": {"ru": "Astana-region", "kk": "", "en": ""},
            "children": [{"id": 8, "name": {"ru": "Esil", "kk": "", "en": ""}, "children": []}],
        }
    )
    tree[0]["children"][0]["children"].append({"id": 9, "name": {"ru": "Esil", "kk": "", "en": ""}, "children": []})
    return tree


def test_ambiguous_city_is_left_alone_instead_of_proposed():
    # Two cities share the name, so "no single match" means "pick one", not "add another".
    client, location_id = _resolve(_candidate(country="Kazakhstan", city="Esil"), tree=_tree_with_twin_cities())
    assert location_id is None
    assert client.places == []


def test_ambiguous_city_does_not_multiply_across_candidates():
    client, tree = _FakeClient(), _tree_with_twin_cities()
    cities = flatten_cities(tree)
    for _ in range(3):
        _resolve_location(client, tree, cities, _candidate(country="Kazakhstan", city="Esil"))
    assert client.places == []  # a third namesake would make every later candidate ambiguous too


def test_namesake_city_in_another_region_is_proposed_not_reused():
    """Two towns share a name in different regions; the second must not inherit the first's id."""
    client, tree = _FakeClient(), _tree()
    cities = flatten_cities(tree)
    first = _candidate(country="Kazakhstan", region="Almaty-region", city="Troitsk")
    second = _candidate(country="Kazakhstan", region="Astana-region", city="Troitsk")
    tree[0]["children"].append({"id": 7, "name": {"ru": "Astana-region", "kk": "", "en": ""}, "children": []})
    _resolve_location(client, tree, cities, first)
    _resolve_location(client, tree, cities, second)
    assert client.places == [(2, "Troitsk"), (7, "Troitsk")]


def test_placeholder_names_are_never_created():
    """The model may echo the site's own catch-all; creating a namesake shadows the system node."""
    for kwargs in (
        {
            "country": "Kazakhstan",
            "region": "Almaty-region",
            "city": "\u0414\u0440\u0443\u0433\u043e\u0439 \u0433\u043e\u0440\u043e\u0434",
        },
        {
            "country": "Kazakhstan",
            "region": "\u0414\u0440\u0443\u0433\u043e\u0439 \u0440\u0435\u0433\u0438\u043e\u043d",
            "city": "Esik",
        },
    ):
        client, location_id = _resolve(_candidate(**kwargs))
        assert location_id is None
        assert client.places == []


def test_a_district_is_not_created_as_a_region():
    # "Kirovsky district" is a level below the region; filing it as one buries the real oblast.
    client, location_id = _resolve(
        _candidate(
            country="Kazakhstan",
            region="\u041a\u0438\u0440\u043e\u0432\u0441\u043a\u0438\u0439 \u0440\u0430\u0439\u043e\u043d",
            city="Kobona",
        )
    )
    assert location_id is None
    assert client.places == []


def test_a_proposed_place_carries_every_locale_the_model_gave():
    """A place created in one language only would be proposed again by a source in another."""
    client, tree = _FakeClient(), _tree()
    cities = flatten_cities(tree)
    _resolve_location(
        client,
        tree,
        cities,
        _candidate(
            country="Kazakhstan",
            region="Almaty-region",
            city="Karakol",
            city_kk="Qaraqol",
            city_en="Karakol-en",
        ),
    )
    assert client.locales == [("Karakol", "Qaraqol", "Karakol-en")]
    # Every spelling is indexed, so the next source naming it differently matches instead of adding.
    assert match_city(cities, "Qaraqol") == match_city(cities, "Karakol-en") == 101


def test_geography_left_behind_by_a_failed_event_post_is_named():
    """Pending nodes outliving their event must be traceable, not anonymous queue entries."""
    client, tree = _FakeClient(), _tree()
    cities, created = flatten_cities(tree), []
    _resolve_location(
        client,
        tree,
        cities,
        _candidate(country="Kazakhstan", region="Zhetysu", city="Taldykorgan"),
        created=created,
    )
    assert created == ["region 'Zhetysu' (#101)", "city 'Taldykorgan' (#102)"]


def test_a_placeholder_in_any_locale_blocks_the_proposal():
    """The name is posted in all three locales, so a clean Russian answer is not enough."""
    client, location_id = _resolve(
        _candidate(
            country="Kazakhstan",
            region="Almaty-region",
            city="Kobona",
            city_kk="\u0411\u0430\u0441\u049b\u0430 \u049b\u0430\u043b\u0430",  # "Basqa qala"
        )
    )
    assert location_id is None
    assert client.places == []


def test_a_punctuation_only_region_or_city_is_refused():
    """ "-" and "()" are non-empty but normalize to nothing; they must not become locations."""
    for kwargs in (
        {"country": "Kazakhstan", "region": "-", "city": "Almaty-town"},
        {"country": "Kazakhstan", "region": "Almaty-region", "city": "()"},
    ):
        client, location_id = _resolve(_candidate(**kwargs))
        assert location_id is None
        assert client.places == []


def test_enrich_fills_a_venue_coordinate_from_the_linked_track():
    """A venue with no coordinate gets the track's start point; the model's own coord is left alone."""

    from agent.run import _add_start_coordinate

    page = "some text\n\nLinks on the page:\nhttps://8.8.8.8/2026/brm.kml"
    import agent.run as run

    kml = "<kml><Placemark><LineString><coordinates>73.08371,49.80972,0</coordinates></LineString></Placemark></kml>"
    orig = run.fetch.fetch_track

    def _fake_track(url):
        return kml

    run.fetch.fetch_track = _fake_track
    try:
        withco = _add_start_coordinate(_candidate(city="Karaganda", venue="Palace"), page)
        assert (withco.lat, withco.lng) == (49.80972, 73.08371)
        # An event with no venue, or one that already has a coordinate, is untouched.
        assert _add_start_coordinate(_candidate(city="Karaganda"), page).lat is None
        keeps = _add_start_coordinate(_candidate(city="K", venue="V", lat=1.0, lng=2.0), page)
        assert (keeps.lat, keeps.lng) == (1.0, 2.0)
    finally:
        run.fetch.fetch_track = orig


def test_enrich_uses_the_models_url_route_when_the_page_lists_no_track():
    """The route the model picked out (url_route) must be tried even if the page text lists no link."""
    import agent.run as run

    seen: list = []

    def _fake_start(links, fetch):
        seen.extend(links)
        return (49.80972, 73.08371)

    orig = run.geo.start_coordinate
    run.geo.start_coordinate = _fake_start
    try:
        cand = _candidate(city="Karaganda", venue="Palace", url_route="https://8.8.8.8/2026/brm.gpx")
        out = run._add_start_coordinate(cand, "text with no links block")
        assert (out.lat, out.lng) == (49.80972, 73.08371)
        assert seen[0] == "https://8.8.8.8/2026/brm.gpx"  # url_route is tried first
    finally:
        run.geo.start_coordinate = orig
