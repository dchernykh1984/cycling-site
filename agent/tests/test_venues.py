"""Where the venue matcher draws the line between one place written twice and two places.

The overlap threshold is the only number in the matcher that is a judgement rather than a fact, and
it was set by measuring: each of the site's 230 venues compared against the others in its own city,
the way the agent asks -- a name, no coordinates. 0.7 merges only real duplicates; 0.65 starts
merging different places. Both halves are pinned here, because the margin is a single step and a
reader tempted to nudge it further should hear it from a failing test rather than from a moderator.

The names are the site's own, escaped because these sources are ASCII-only, and glossed above each.
"""

import pytest

from agent import venues

SAME_PLACE = [
    (
        # the duplicate that started this: three words of four, which is 0.75
        ("\u041c\u0430\u0433\u0430\u0437\u0438\u043d Giant, \u0410\u0431\u0430\u044f 47"),
        ("Giant (\u043f\u0440. \u0410\u0431\u0430\u044f, 47), \u0410\u043b\u043c\u0430\u0442\u044b"),
        "the duplicate that started this: three words of four, which is 0.75",
    ),
    (
        # Tula: the one pair 0.7 adds over 0.8
        (
            "\u0426\u0435\u043d\u0442\u0440\u0430\u043b\u044c\u043d\u044b\u0439 "
            "\u043f\u0430\u0440\u043a \u0438\u043c. \u041f.\u041f. \u0411\u0435"
            "\u043b\u043e\u0443\u0441\u043e\u0432\u0430"
        ),
        (
            "\u0426\u041f\u041a\u0438\u041e \u0438\u043c. \u041f. \u041f. \u0411"
            "\u0435\u043b\u043e\u0443\u0441\u043e\u0432\u0430"
        ),
        "Tula: the one pair 0.7 adds over 0.8",
    ),
    (
        # recognised at 0.8 already, and still is
        (
            "\u041f\u0430\u0440\u043a\u043e\u0432\u043a\u0430 Halyk Bank (\u043f"
            "\u0440. \u0410\u043b\u044c-\u0424\u0430\u0440\u0430\u0431\u0438 40)"
        ),
        ("\u0443\u043b. \u0410\u043b\u044c-\u0424\u0430\u0440\u0430\u0431\u0438 40, Halyk Bank"),
        "recognised at 0.8 already, and still is",
    ),
]

DIFFERENT_PLACES = [
    (
        # two different squares in Almaty
        (
            "\u041f\u043b\u043e\u0449\u0430\u0434\u044c \u0410\u0441\u0442\u0430"
            "\u043d\u0430 (\u0410\u043b\u043c\u0430\u0442\u044b)"
        ),
        (
            "\u041f\u043b\u043e\u0449\u0430\u0434\u044c \u0420\u0435\u0441\u043f"
            "\u0443\u0431\u043b\u0438\u043a\u0438 (\u0410\u043b\u043c\u0430\u0442"
            "\u044b)"
        ),
        "two different squares in Almaty",
    ),
    (
        # two corners of one avenue, some way apart
        ("\u0443\u043b. \u0410\u043b\u044c-\u0424\u0430\u0440\u0430\u0431\u0438 40, Halyk Bank"),
        (
            "\u041e\u0441\u0442\u0430\u043d\u043e\u0432\u043a\u0430 \u0443 Halyk Ba"
            "nk, \u0421\u0435\u0439\u0444\u0443\u043b\u043b\u0438\u043d\u0430 / "
            "\u0410\u043b\u044c-\u0424\u0430\u0440\u0430\u0431\u0438"
        ),
        "two corners of one avenue, some way apart",
    ),
    (
        # two different palaces of culture in Karaganda
        (
            "\u0414\u0432\u043e\u0440\u0435\u0446 \u043a\u0443\u043b\u044c\u0442"
            "\u0443\u0440\u044b \u0433\u043e\u0440\u043d\u044f\u043a\u043e\u0432"
        ),
        (
            "\u0414\u0432\u043e\u0440\u0435\u0446 \u043a\u0443\u043b\u044c\u0442"
            "\u0443\u0440\u044b \u041c\u0430\u0439\u043a\u0443\u0434\u0443\u043a"
            "\u0430"
        ),
        "two different palaces of culture in Karaganda",
    ),
]


@pytest.mark.parametrize(("first", "second", "why"), SAME_PLACE)
def test_two_spellings_of_one_place_are_recognised(first, second, why):
    assert venues.same_name(first, second), why


@pytest.mark.parametrize(("first", "second", "why"), DIFFERENT_PLACES)
def test_two_different_places_are_left_apart(first, second, why):
    """These are what a lower threshold would merge -- the reason 0.7 is the floor, not a start."""
    assert not venues.same_name(first, second), why


@pytest.mark.parametrize(("first", "second", "why"), DIFFERENT_PLACES)
def test_they_are_held_apart_by_the_threshold_and_nothing_else(first, second, why):
    """Proof that this number is what keeps them apart: loosen it and they merge."""
    original = venues._NAME_OVERLAP
    venues._NAME_OVERLAP = 0.6
    try:
        assert venues.same_name(first, second), f"expected {why} to merge once the threshold is loosened"
    finally:
        venues._NAME_OVERLAP = original


def test_the_threshold_is_where_the_measurement_left_it():
    """A bare pin, so moving the number is a deliberate act with the tests above to answer to."""
    assert venues._NAME_OVERLAP == 0.7
