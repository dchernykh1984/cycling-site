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


def test_match_region_keeps_krai_and_republic_distinct():
    """ "Altai Krai" and "Altai Republic" share a core but are different federal subjects."""
    country = {
        "id": 1,
        "name": {"ru": "Russia", "kk": "", "en": "Russia"},
        "children": [
            {"id": 2, "name": {"ru": "", "kk": "", "en": "Altai Krai"}, "children": []},
        ],
    }
    assert match_region(country, "Altai Republic") is None  # a different subject -> propose it
    assert match_region(country, "Altai Krai")["id"] == 2  # the one that is stored, reworded


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


def test_a_country_written_as_a_code_still_finds_its_cities():
    """A model asked for a country sometimes answers "KZ", and a code matches no name at all.

    It is not a substring of "Kazakhstan" and is too short for the five-character opening rule, so
    the country filter used to drop every candidate and the event reached the site with no place --
    which is exactly how a real skiing session arrived unplaced.
    """
    cities = flatten_cities(_tree())
    assert match_city(cities, "Uniquely-Almaty", country="KZ") == 3
    assert match_city(cities, "Uniquely-Almaty", country="kz") == 3
    assert match_city(cities, "Uniquely-Almaty", country="Kazakhstan") == 3


def test_a_code_for_another_country_still_filters_the_city_out():
    """The code must resolve the name, not wave the filter through."""
    cities = flatten_cities(_tree())
    assert match_city(cities, "Uniquely-Almaty", country="RU") is None


def test_a_country_node_is_found_by_its_code_too():
    tree = _tree_with_catch_alls()
    assert match_country(tree, "KZ")["id"] == 1
    assert match_country(tree, "kg")["id"] == 6  # Kyrgyzstan


def test_canonical_country_leaves_a_real_name_alone():
    from agent.locations import canonical_country

    assert canonical_country("Kazakhstan") == "Kazakhstan"
    assert canonical_country("") == ""
    assert canonical_country("KZ") == "kazakhstan"


# The site stores Ulytau Region's Russian name beginning with the Kazakh letter U-hook, and a model
# writing Russian spells it with the ordinary Russian U. On the raw letters those read as two
# different regions: the agent proposed a second Ulytau Region and a second Zhezkazgan beneath it,
# neither with coordinates, and filed a race there. Names are escaped because this file is ASCII-only
# and glossed above each.
# "Ulytauskaya oblast", Russian U
_RU_SPELLING = "\u0423\u043b\u044b\u0442\u0430\u0443\u0441\u043a\u0430\u044f \u043e\u0431\u043b\u0430\u0441\u0442\u044c"
# the same, with the Kazakh U-hook -- what the site stores
_KK_SPELLING = "\u04b0\u043b\u044b\u0442\u0430\u0443\u0441\u043a\u0430\u044f \u043e\u0431\u043b\u0430\u0441\u0442\u044c"
_KK_OWN_NAME = "\u0423\u043b\u044b\u0442\u0430\u0443 \u043e\u0431\u043b\u044b\u0441\u044b"  # "Ulytau oblysy"
_CITY = "\u0416\u0435\u0437\u043a\u0430\u0437\u0433\u0430\u043d"  # "Zhezkazgan"


def _ulytau_tree():
    return [
        {
            "id": 1,
            "name": {
                "ru": "\u041a\u0430\u0437\u0430\u0445\u0441\u0442\u0430\u043d",
                "kk": "\u049a\u0430\u0437\u0430\u049b\u0441\u0442\u0430\u043d",
                "en": "Kazakhstan",
            },
            "children": [
                {
                    "id": 225,
                    "name": {"ru": _KK_SPELLING, "kk": _KK_OWN_NAME, "en": "Ulytau Region"},
                    "children": [
                        {
                            "id": 226,
                            "name": {
                                "ru": _CITY,
                                "kk": "\u0416\u0435\u0437\u049b\u0430\u0437\u0493\u0430\u043d",
                                "en": "Zhezkazgan",
                            },
                            "children": [],
                        }
                    ],
                }
            ],
        }
    ]


def test_a_region_written_in_either_script_finds_the_one_node():
    tree = _ulytau_tree()
    country = match_country(tree, "Kazakhstan")
    for spelling in (_RU_SPELLING, _KK_SPELLING, _KK_OWN_NAME, "Ulytau Region"):
        assert match_region(country, spelling) is not None, spelling
        assert match_region(country, spelling)["id"] == 225, spelling


def test_the_city_is_found_once_its_region_is():
    """The region is a filter on the city, so a missed region loses the city with it -- which is how
    both came to be proposed a second time."""
    tree = _ulytau_tree()
    cities = flatten_cities(tree)
    for spelling in (_RU_SPELLING, _KK_SPELLING, "Ulytau Region"):
        assert match_city(cities, _CITY, spelling, "Kazakhstan") == 226, spelling


def test_two_regions_that_differ_by_more_than_a_letter_stay_apart():
    """Folding must not reach past spelling: these pairs are genuinely different regions."""
    for first, second in (
        (
            "\u0410\u043b\u0442\u0430\u0439\u0441\u043a\u0438\u0439 \u043a\u0440\u0430\u0439",
            "\u0420\u0435\u0441\u043f\u0443\u0431\u043b\u0438\u043a\u0430 \u0410\u043b\u0442\u0430\u0439",
        ),  # Altai Krai / Altai Republic
        (
            "\u041d\u0435\u043d\u0435\u0446\u043a\u0438\u0439"
            " \u0430\u0432\u0442\u043e\u043d\u043e\u043c\u043d\u044b\u0439 \u043e\u043a\u0440\u0443\u0433",
            "\u042f\u043c\u0430\u043b\u043e-\u041d\u0435\u043d\u0435\u0446\u043a\u0438\u0439"
            " \u0430\u0432\u0442\u043e\u043d\u043e\u043c\u043d\u044b\u0439 \u043e\u043a\u0440\u0443\u0433",
        ),  # Nenets / Yamalo-Nenets autonomous okrug
    ):
        tree = [
            {
                "id": 1,
                "name": {"ru": "\u0420\u043e\u0441\u0441\u0438\u044f", "kk": "", "en": "Russia"},
                "children": [
                    {"id": 10, "name": {"ru": first, "kk": "", "en": ""}, "children": []},
                    {"id": 11, "name": {"ru": second, "kk": "", "en": ""}, "children": []},
                ],
            }
        ]
        country = match_country(tree, "Russia")
        assert match_region(country, first)["id"] == 10, first
        assert match_region(country, second)["id"] == 11, second


def test_the_tables_keyed_on_cyrillic_still_match():
    """The placeholder, district and country tables are keyed on the raw letters and are matched
    with normalize_name, not the folding. Folding one side of those without the other would stop
    them matching at all -- silently, since nothing else would fail."""
    from agent.locations import canonical_country, is_placeholder_name, looks_like_district

    assert is_placeholder_name("\u0414\u0440\u0443\u0433\u0430\u044f \u043e\u0431\u043b\u0430\u0441\u0442\u044c"), (
        "the site's own catch-all name"
    )
    assert looks_like_district(
        "\u041a\u0438\u0440\u043e\u0432\u0441\u043a\u0438\u0439 \u0440\u0430\u0439\u043e\u043d"
    ), "a district must not become a region"
    assert canonical_country("\u041a\u0438\u0440\u0433\u0438\u0437\u0438\u044f") == "kyrgyzstan"
    assert canonical_country("KZ") == "kazakhstan"


def test_folding_lower_cases_before_it_transliterates():
    """The transliteration table is keyed on the lower-case letters, so an upper-case one handed to
    it comes back untouched. Getting this order wrong made the fix do nothing while every test
    still passed."""
    from agent.locations import fold_name

    assert fold_name(_RU_SPELLING) == fold_name(_KK_SPELLING)
    assert fold_name(_RU_SPELLING).isascii(), fold_name(_RU_SPELLING)


def test_a_town_proposed_earlier_in_the_run_is_found_again():
    """city_record exists so a second source naming the same town reuses it. Its names have to be
    folded like every other record, or the reuse misses and the town is proposed twice -- the very
    fault this folding was added to end.

    The record stands alone here: adding it beside the tree's own Zhezkazgan would make the name
    ambiguous, and the matcher would rightly refuse both."""
    tree = _ulytau_tree()
    region = tree[0]["children"][0]
    # All three locales carry the Cyrillic name: that is what propose_city posts when the model
    # gives no translation, and it is the case a raw record would lose.
    proposed = [city_record(999, (_CITY, _CITY, _CITY), region, tree[0])]
    for spelling in (_RU_SPELLING, _KK_SPELLING, "Ulytau Region"):
        assert match_city(proposed, _CITY, spelling, "Kazakhstan") == 999, spelling
    # And the town is reachable by its Latin spelling too, which is what folding buys.
    assert match_city(proposed, "Zhezkazgan", _RU_SPELLING, "Kazakhstan") == 999
