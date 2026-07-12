from agent.locations import flatten_cities, match_city, normalize_name


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


def test_match_city_hint_never_overrides_unique_match():
    cities = flatten_cities(_tree())
    # Astana is unique, so a wrong region hint must not break the match.
    assert match_city(cities, "Astana", region="no-such-region") == 5


def test_match_city_unknown_or_empty_returns_none():
    cities = flatten_cities(_tree())
    assert match_city(cities, "Paris") is None
    assert match_city(cities, "") is None
    assert match_city([], "dup-city") is None
