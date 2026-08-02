"""Recognising that a post's meeting point is a place the site already carries.

Every name and distance below is one this site actually holds. The rule they measure: the name
decides whether two venues are one place, and the distance vetoes. Neither works alone -- two
different places sit 43 m apart here while two spellings of one place sit 75 m apart, and
"Industrialka" is a district some 5 km across whose two nodes are two real start lines 2.8 km apart.

Names are written transliterated so this file stays ASCII like the rest of the source; the one test
that is *about* Cyrillic builds its string from code points.
"""

import time

from instagram_agent.geo import (
    city_point,
    distance_metres,
    existing_venue,
    same_name,
    same_place,
    venues_of,
)

# The Almaty car park this site carried four times over, once per announcement that mentioned it.
HALYK = (43.225803, 76.942106)
CAR_PARK = "Parkovka Halyk Bank (pr. Al-Farabi 40)"
SAME_CAR_PARK = "ul. Al-Farabi 40, Halyk Bank"
AS_A_POST_WROTE_IT = "ul. Al-Farabi, 40 (parkovka Halyk Banka)"
VELODROME = "Velotrek im. A.Vinokurova"
# The two "Industrialka" start lines, as the site holds them.
INDUSTRIALKA_ONE = (43.300876, 76.802351)
INDUSTRIALKA_TWO = (43.323669, 76.816350)


def _tree(*venues):
    return [
        {
            "id": 1,
            "name": {"ru": "Kazakhstan"},
            "children": [
                {
                    "id": 2,
                    "name": {"ru": "Almaty region"},
                    "children": [
                        {
                            "id": 3,
                            "name": {"ru": "Almaty"},
                            "lat": "43.236392",
                            "lng": "76.945728",
                            "children": list(venues),
                        }
                    ],
                }
            ],
        }
    ]


def _venue(venue_id, name, point=None):
    node = {"id": venue_id, "name": {"ru": name, "en": name}}
    if point:
        node["lat"], node["lng"] = str(point[0]), str(point[1])
    return node


# --- what the names say ---------------------------------------------------------------------------


def test_one_car_park_written_three_ways_is_one_name():
    assert same_name(CAR_PARK, SAME_CAR_PARK)
    assert same_name(AS_A_POST_WROTE_IT, SAME_CAR_PARK)
    assert same_name(AS_A_POST_WROTE_IT, CAR_PARK)


def test_a_cyrillic_spelling_matches_the_latin_one_on_the_same_sign():
    """Halyk on the sign and its Cyrillic spelling drift apart unless kh is folded onto h."""
    codes = (
        0x425,
        0x430,
        0x43B,
        0x44B,
        0x43A,
        0x20,
        0x411,
        0x430,
        0x43D,
        0x43A,
        0x20,
        0x410,
        0x440,
        0x435,
        0x43D,
        0x430,
    )  # "Halyk Bank Arena" in Cyrillic
    assert same_name("".join(chr(code) for code in codes), "Halyk Bank Arena")


def test_a_trailing_qualifier_does_not_make_another_place():
    assert same_name("Shar EXPO (Nur-Alem), Astana", "Shar EXPO")


def test_a_grammatical_ending_is_not_another_word():
    """A Russian caption declines the name -- "Halyk Banka" is the bank on the sign."""
    assert same_name("parkovka Halyk Banka", "Halyk Bank")
    assert not same_name("Halyk Bank", "Halyk Arena"), "sharing one word is not sharing a place"


def test_sharing_a_street_is_not_sharing_a_start_line():
    assert not same_name(AS_A_POST_WROTE_IT, "Park Pervogo Prezidenta (ost. Al-Farabi)")


def test_a_name_of_one_word_says_too_little_on_its_own():
    assert not same_name("Industrialka", "Industrialka")


# --- what the distance says -----------------------------------------------------------------------


def test_distance_is_unknown_when_either_point_is():
    assert distance_metres(None, HALYK) is None
    assert distance_metres(HALYK, None) is None


def test_the_same_point_is_no_distance_apart():
    assert distance_metres(HALYK, HALYK) == 0


def test_distance_is_measured_in_metres():
    assert 2700 < distance_metres(INDUSTRIALKA_ONE, INDUSTRIALKA_TWO) < 2900


# --- the two together -------------------------------------------------------------------------------


def test_the_car_park_is_recognised_even_with_no_point_of_our_own():
    """The geocoder may not answer; a name the site already knows is still enough."""
    assert same_place(AS_A_POST_WROTE_IT, None, SAME_CAR_PARK, HALYK)


def test_two_start_lines_in_one_district_stay_apart_despite_one_name():
    """Industrialka is a district, and clubs name the exact corner they meet at."""
    assert not same_place("Industrialka", INDUSTRIALKA_ONE, "Industrialka", INDUSTRIALKA_TWO)


def test_next_door_a_single_distinctive_word_is_enough():
    """Compass and Magazin Compass are one shop, and the site holds both at one point."""
    assert same_place("Compass", (43.262386, 76.984031), "Magazin Compass", (43.262386, 76.984031))


def test_being_close_is_not_enough_without_a_word_in_common():
    """These two sit 43 m apart on this site and are different places."""
    assert not same_place("Bereg reki Ili", (43.9, 77.0), "Urochishche Tamgaly Tas", (43.9004, 77.0))


def test_a_matching_name_far_away_is_refused():
    assert not same_place(CAR_PARK, (43.9, 77.0), SAME_CAR_PARK, HALYK)


# --- reading the site's own tree ---------------------------------------------------------------------


def test_the_venue_already_there_is_found():
    tree = _tree(_venue(100, SAME_CAR_PARK, HALYK), _venue(101, VELODROME, (43.258907, 76.969335)))
    assert existing_venue(venues_of(tree, 3), AS_A_POST_WROTE_IT, HALYK) == 100


def test_a_place_the_site_does_not_have_is_not_invented():
    tree = _tree(_venue(100, VELODROME, (43.258907, 76.969335)))
    assert existing_venue(venues_of(tree, 3), AS_A_POST_WROTE_IT, HALYK) is None


def test_a_venue_with_no_coordinates_can_still_be_recognised():
    """Most of this site's venues carry a point, but not all; the rest are still places we know."""
    tree = _tree(_venue(100, SAME_CAR_PARK))
    assert existing_venue(venues_of(tree, 3), AS_A_POST_WROTE_IT, HALYK) == 100


def test_an_empty_or_unnamed_venue_matches_nothing():
    tree = _tree(_venue(100, SAME_CAR_PARK, HALYK))
    assert existing_venue(venues_of(tree, 3), "", HALYK) is None
    assert existing_venue(venues_of(tree, 3), "-", HALYK) is None


def test_venues_of_an_unknown_city_is_empty_rather_than_an_error():
    assert venues_of(_tree(_venue(100, SAME_CAR_PARK)), 999) == []
    assert venues_of([], 3) == []


def test_a_city_gives_up_its_own_point_for_checking_a_geocoder():
    assert city_point(_tree(), 3) == (43.236392, 76.945728)
    assert city_point(_tree(), 999) is None


def test_the_geocoder_is_asked_no_faster_than_it_allows():
    """Nominatim asks for one request a second, and a run can read a dozen announcements at once."""
    import instagram_agent.geo as module

    slept: list[float] = []
    now = [1000.0]
    original_sleep, original_clock = time.sleep, time.monotonic

    def _record(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    try:
        time.sleep = _record
        time.monotonic = lambda: now[0]
        module._asked_at = 0.0
        module._wait_our_turn()  # the first call waits for nobody
        assert slept == []
        now[0] += 0.2
        module._wait_our_turn()  # a second one, straight after, waits out the rest of the second
        assert slept and 0.7 < slept[0] <= 1.0
    finally:
        time.sleep, time.monotonic = original_sleep, original_clock
        module._asked_at = 0.0
