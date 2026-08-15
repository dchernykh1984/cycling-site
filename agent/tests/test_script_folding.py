"""One name written in two scripts has to read as one word.

The site grew four separate nodes for a single filling station on the Almaty ring road because the
sign says Compass and the announcements say Kompas: transliteration turns the Cyrillic spelling into
"kompas" and leaves the Latin one as "compass", and those two share not a single letter position.
``fold_script`` puts both on one form.

Each rule below is a pair this site or its sources actually carry. The folding runs on a word that
has already been transliterated, so it never has to know which script the name came from.

The names are escaped because these sources are ASCII-only, and glossed above each.
"""

import pytest

from agent import venues

JOINED = [
    (
        # the filling station this whole thing is about
        "\u041a\u043e\u043c\u043f\u0430\u0441",
        "Compass",
        "the filling station this whole thing is about",
    ),
    (
        # one shop, one script each way
        ("\u041c\u0430\u0433\u0430\u0437\u0438\u043d \u041a\u043e\u043c\u043f\u0430\u0441"),
        "\u041c\u0430\u0433\u0430\u0437\u0438\u043d Compass",
        "one shop, one script each way",
    ),
    (
        # kh folds onto h
        "\u0425\u0430\u043b\u044b\u043a",
        "Halyk",
        "kh folds onto h",
    ),
    (
        # x folds onto ks
        "\u041c\u0430\u043a\u0441\u0438\u043c",
        "Maxim",
        "x folds onto ks",
    ),
    (
        # w folds onto v
        "\u0412\u043e\u043b\u044c\u0444",
        "Wolf",
        "w folds onto v",
    ),
    (
        # ph folds onto f
        "\u0421\u043e\u0444\u0438\u044f",
        "Sophia",
        "ph folds onto f",
    ),
    (
        # dzh folds onto j, y onto i
        "\u0414\u0436\u0430\u0439\u043b\u0430\u0443",
        "Jailau",
        "dzh folds onto j, y onto i",
    ),
    (
        # q folds onto k
        "\u049a\u0430\u0437\u0430\u049b\u0441\u0442\u0430\u043d",
        "Qazaqstan",
        "q folds onto k",
    ),
    (
        # y folds onto i on both sides
        "\u0414\u043e\u0441\u0442\u044b\u043a",
        "Dostyk",
        "y folds onto i on both sides",
    ),
    (
        # c is a k sound before a back vowel
        "\u041a\u0430\u0444\u0435",
        "Cafe",
        "c is a k sound before a back vowel",
    ),
]

KEPT_APART = [
    (
        # two spellings that are genuinely different words
        "\u041c\u0435\u0434\u0435\u0443",
        "\u041c\u0435\u0434\u0435\u043e",
        "two spellings that are genuinely different words",
    ),
    (
        # a shared first letter is not a shared name
        "\u041a\u043e\u043c\u043f\u0430\u0441",
        "\u041a\u043e\u0441\u043c\u043e\u0441",
        "a shared first letter is not a shared name",
    ),
    (
        # short words must not collapse into each other
        "\u041f\u0430\u0440\u043a",
        "\u041f\u043e\u0440\u0442",
        "short words must not collapse into each other",
    ),
]


@pytest.mark.parametrize(("cyrillic", "latin", "why"), JOINED)
def test_both_spellings_fold_onto_one_word(cyrillic, latin, why):
    assert venues.venue_words(cyrillic) == venues.venue_words(latin), why


@pytest.mark.parametrize(("first", "second", "why"), KEPT_APART)
def test_folding_does_not_run_two_different_words_together(first, second, why):
    assert venues.venue_words(first) != venues.venue_words(second), why


def test_the_case_that_grew_four_nodes_is_now_one_place():
    """ "Kompas" the filling station, at one point, under either spelling."""
    voad = (43.262386, 76.984032)
    assert venues.same_place("\u041a\u043e\u043c\u043f\u0430\u0441", voad, "Compass", voad)


def test_a_venue_named_in_the_other_script_is_reused_rather_than_added_again():
    """What the folding is for: the agent finds the node the site already has."""
    known = [
        {
            "id": 1414,
            # "AZS Kompas (VOAD)" -- the node the site keeps
            "names": ["\u0410\u0417\u0421 \u00ab\u041a\u043e\u043c\u043f\u0430\u0441\u00bb (\u0412\u041e\u0410\u0414)"],
            "point": (43.262386, 76.984032),
        }
    ]
    # "Magazin Compass" -- the same corner, written the other way round
    written_differently = "\u041c\u0430\u0433\u0430\u0437\u0438\u043d Compass"
    assert venues.existing_venue(known, written_differently, (43.262386, 76.984031)) == 1414


def test_a_word_with_nothing_to_fold_comes_through_as_it_was():
    """Most names hold nothing the rules touch, and those must come through unchanged."""
    for word in ("medeu", "arena", "park", "start", "most"):
        assert venues.fold_script(word) == word


def test_folding_is_idempotent():
    """Folding a folded word must not keep changing it, or two runs would disagree."""
    for word in ("kompas", "shimbulak", "halik", "maksim", "jailau"):
        assert venues.fold_script(venues.fold_script(word)) == venues.fold_script(word)


def test_it_is_the_y_rule_that_touches_a_name_like_shymbulak():
    """Named rather than hidden: "shymbulak" does change, because both spellings fold alike."""
    assert venues.fold_script("shymbulak") == "shimbulak"
    assert venues.fold_script("shimbulak") == "shimbulak"
