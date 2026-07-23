from agent.locations import (
    city_record,
    flatten_cities,
    match_city,
    match_country,
    match_region,
    normalize_name,
)


def _tree():
    # Two cities share the name "dup-city" (ids 3 and 8) to exercise ambiguity handling.
    return [
        {
            "id": 1,
            "name": {"ru": "kazakhstan-ru", "kk": "kazakhstan-kk", "en": "Kazakhstan"},
            "children": [
                {
                    "id": 2,
                    "name": {"ru": "almaty-region", "kk": "", "en": ""},
                    "children": [
                        {"id": 3, "name": {"ru": "dup-city", "kk": "", "en": "Uniquely-Almaty"}, "children": []},
                    ],
                },
                {
                    "id": 4,
                    "name": {"ru": "astana-region", "kk": "", "en": ""},
                    "children": [
                        {"id": 5, "name": {"ru": "Astana-ru", "kk": "", "en": "Astana"}, "children": []},
                    ],
                },
            ],
        },
        {
            "id": 6,
            "name": {"ru": "kyrgyzstan-ru", "kk": "", "en": "Kyrgyzstan"},
            "children": [
                {
                    "id": 7,
                    "name": {"ru": "chuy-region", "kk": "", "en": ""},
                    "children": [
                        {"id": 8, "name": {"ru": "dup-city", "kk": "", "en": ""}, "children": []},
                    ],
                }
            ],
        },
    ]


def test_normalize_name_ignores_case_punctuation_whitespace():
    assert normalize_name("  Alma-Ata! ") == normalize_name("alma ata")


def test_flatten_cities_returns_only_depth3_nodes():
    cities = flatten_cities(_tree())
    assert sorted(c["id"] for c in cities) == [3, 5, 8]


def test_match_city_exact_by_any_locale():
    cities = flatten_cities(_tree())
    assert match_city(cities, "Astana") == 5  # via the English locale
    assert match_city(cities, "uniquely-almaty") == 3


def test_match_city_ambiguous_returns_none():
    cities = flatten_cities(_tree())
    assert match_city(cities, "dup-city") is None  # ids 3 and 8 share the name


def test_match_city_region_disambiguates():
    cities = flatten_cities(_tree())
    assert match_city(cities, "dup-city", region="chuy-region") == 8


def test_match_city_country_disambiguates():
    cities = flatten_cities(_tree())
    assert match_city(cities, "dup-city", country="Kyrgyzstan") == 8


def test_match_city_rejects_a_unique_namesake_in_another_region():
    """A namesake in the wrong region is worse than no match: the race would be filed there.

    Proposing a second city instead puts the decision in front of a human.
    """
    cities = flatten_cities(_tree())
    assert match_city(cities, "Astana", region="no-such-region") is None
    assert match_city(cities, "Astana", region="astana-region") == 5


def test_match_city_tolerates_how_sources_abbreviate_a_region():
    cities = flatten_cities(_tree())
    # "almaty-reg" vs the tree's "almaty-region": same opening, so still the same place.
    assert match_city(cities, "uniquely-almaty", region="almaty-reg") == 3


def test_match_city_unknown_or_empty_returns_none():
    cities = flatten_cities(_tree())
    assert match_city(cities, "Paris") is None
    assert match_city(cities, "") is None
    assert match_city([], "dup-city") is None


def _tree_with_catch_alls():
    tree = _tree()
    tree.append(
        {
            "id": 90,
            "name": {"ru": "other-country-ru", "kk": "", "en": "Other country"},
            "children": [{"id": 91, "name": {"ru": "x", "kk": "", "en": "Other region"}, "children": []}],
        }
    )
    tree[0]["children"].append({"id": 92, "name": {"ru": "y", "kk": "", "en": "Other region"}, "children": []})
    return tree


def test_match_country_by_name_and_catch_all_fallback():
    tree = _tree_with_catch_alls()
    assert match_country(tree, "Kyrgyzstan")["id"] == 6
    # A country the site does not carry lands under the catch-all: the agent never creates a root.
    assert match_country(tree, "Iceland")["id"] == 90
    # An unnamed country is a different case: guessing would file a real region under the catch-all.
    assert match_country(tree, "") is None


def test_match_country_without_catch_all_returns_none():
    assert match_country(_tree(), "Iceland") is None


def test_match_region_and_catch_all():
    tree = _tree_with_catch_alls()
    kazakhstan = match_country(tree, "Kazakhstan")
    assert match_region(kazakhstan, "astana-region")["id"] == 4
    assert match_region(kazakhstan, "no-such-region") is None  # unknown -> the caller proposes it


def test_city_record_is_matchable_right_away():
    tree = _tree_with_catch_alls()
    country = match_country(tree, "Kazakhstan")
    region = match_region(country, "astana-region")
    cities = flatten_cities(tree)
    cities.append(city_record(77, "Kobona", region, country))
    assert match_city(cities, "kobona") == 77


def test_country_aliases_reach_the_real_country_not_the_catch_all():
    """Russian sources write "Kirgiziya"/"Belorussiya"; the tree holds the official names.

    Without the alias the country looks unknown, so the race is filed under the catch-all and every
    town from that source is proposed under the wrong root.
    """
    tree = _tree_with_catch_alls()
    tree.append({"id": 95, "name": {"ru": "Belarus-ru", "kk": "", "en": "Belarus"}, "children": []})
    assert match_country(tree, "\u041a\u0438\u0440\u0433\u0438\u0437\u0438\u044f")["id"] == 6  # Kyrgyzstan
    assert match_country(tree, "\u0411\u0435\u043b\u043e\u0440\u0443\u0441\u0441\u0438\u044f")["id"] == 95
    assert match_country(tree, "Turkiye")["id"] == 90  # no Turkey in this tree -> catch-all


def test_a_city_that_is_its_own_region_survives_an_oblast_hint():
    """Astana is modelled as its own region; sources name the oblast around it.

    Filtering it out would have the agent propose a duplicate of a capital city.
    """
    tree = _tree()
    tree[0]["children"].append(
        {
            "id": 30,
            "name": {"ru": "Capitalcity", "kk": "", "en": ""},
            "children": [{"id": 31, "name": {"ru": "Capitalcity", "kk": "", "en": ""}, "children": []}],
        }
    )
    cities = flatten_cities(tree)
    assert match_city(cities, "Capitalcity", region="Surrounding-oblast") == 31


def test_a_country_named_in_its_long_form_still_finds_the_real_node():
    """ "Republic of Kazakhstan" is the country the tree has, not one it lacks.

    Sending it to the catch-all would file a real oblast under "Other country" for good.
    """
    tree = _tree_with_catch_alls()
    assert match_country(tree, "Kazakhstan-ru official")["id"] == 1
    assert match_country(tree, "Atlantis")["id"] == 90  # genuinely unknown -> catch-all


def test_a_country_sharing_a_prefix_is_not_confused_with_another():
    """ "North Korea" must not resolve to "North Macedonia" on a shared 5-char prefix."""
    tree = [
        {"id": 1, "name": {"ru": "Severnaya Makedoniya", "kk": "", "en": "North Macedonia"}, "children": []},
        {"id": 2, "name": {"ru": "x", "kk": "", "en": "Other country"}, "children": []},
    ]
    assert match_country(tree, "Severnaya Koreya")["id"] == 2  # unknown -> catch-all, not id 1
    assert match_country(tree, "North Macedonia Republic")["id"] == 1  # genuine long form still works


def test_region_hint_disambiguates_two_same_named_cities_one_of_which_is_its_own_region():
    """York-the-county and York-in-Lancashire: a correct region hint must pick the right one."""
    cities = [
        {"id": 10, "names": {"york"}, "region_names": {"york"}, "country_names": {"uk"}},
        {"id": 11, "names": {"york"}, "region_names": {"lancashire"}, "country_names": {"uk"}},
    ]
    assert match_city(cities, "York", region="Lancashire") == 11  # not None, not the self-region one


def test_match_region_tolerates_a_differently_worded_spelling():
    """A region named from the model's knowledge should reuse a stored node spelled a bit differently."""
    country = {
        "id": 1,
        "name": {"ru": "Morocco", "kk": "", "en": "Morocco"},
        "children": [
            {"id": 2, "name": {"ru": "region Marrakesh-Safi", "kk": "", "en": "Marrakesh-Safi"}, "children": []},
            {"id": 3, "name": {"ru": "Rabat-Sale-Kenitra", "kk": "", "en": "Rabat"}, "children": []},
        ],
    }
    assert match_region(country, "Marrakesh-Safi")["id"] == 2  # generic-word strip reuses the node
    assert match_region(country, "marrakesh safi region")["id"] == 2
    assert match_region(country, "Tanger-Tetouan-Al Hoceima") is None  # genuinely new -> propose it


def test_match_region_keeps_two_regions_where_one_name_nests_in_the_other():
    """ "Nenets AO" must not collapse into "Yamalo-Nenets AO" -- they are 2000 km apart."""
    country = {
        "id": 1,
        "name": {"ru": "Russia", "kk": "", "en": "Russia"},
        "children": [
            {"id": 2, "name": {"ru": "", "kk": "", "en": "Yamalo-Nenets autonomous okrug"}, "children": []},
        ],
    }
    assert match_region(country, "Nenets autonomous okrug") is None  # distinct region -> propose it
    assert match_region(country, "Yamalo-Nenets okrug")["id"] == 2  # the same one, reworded
