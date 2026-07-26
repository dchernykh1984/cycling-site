"""Duplicate detection, exercised on the pairs this site actually produced.

Most "is a duplicate" case below is a real rejection made by hand on the site, and every "is not"
case is a pair of genuinely distinct events the agent must keep proposing -- a false match drops a
real race silently, which is the more expensive of the two mistakes.
"""

from agent.dedup import build_index, matching_known, title_tokens

# Rarity is only trusted on a calendar big enough to judge it, so tests that rely on a rare word
# pad the index to that size.
_PADDING = 40


def _event(title, date, city=None, titles=None):
    return {"title": title, "titles": titles or [title], "date_start": date, "city_id": city}


def _index(*events, padded=False):
    filler = [_event(f"Filler Event {n}", "2020-01-01", city=999) for n in range(_PADDING)] if padded else []
    return build_index([*events, *filler])


def test_title_tokens_drops_year_punctuation_and_stopwords():
    assert title_tokens("Apricot Marathon - Gravel & MTB 2026") == {"apricot", "marathon", "gravel", "mtb"}
    assert title_tokens("Championship of Kyrgyzstan on the road 2025") == {"championship", "kyrgyzstan", "road"}


def test_verbose_retitling_same_date_is_duplicate():
    index = _index(_event("Apricot Marathon Gravel MTB 2026", "2026-08-09"))
    assert matching_known(["Apricot Marathon Gravel MTB Race 2026"], "2026-08-09", None, index)


def test_extra_words_but_shared_core_same_date_is_duplicate():
    index = _index(_event("Championship Kyrgyzstan road 2026 UCI", "2026-08-15"))
    candidate = "Championship Kyrgyzstan road cycling 2026 amateurs masters"
    assert matching_known([candidate], "2026-08-15", None, index)


def test_cross_language_duplicate_matches_via_english_variant():
    index = _index(_event("Apricot Marathon Gravel MTB 2026", "2026-08-09"))
    variants = ["Aprikot Marafon 2026", "", "Apricot Marathon Gravel MTB Race 2026"]  # ru, kk, en
    assert matching_known(variants, "2026-08-09", None, index)


def test_a_split_name_matches_the_same_name_written_as_one_word():
    """Event 487 against 383: "OpenBand Trails" is "Open Band Treyly" with the words run together.

    Deliberately without padding, so it is the merged neighbours deciding and not a rare word.
    """
    index = _index(_event("Open Band Treyly Tuman Race 2026", "2026-10-10", city=1834))
    assert matching_known(["OpenBand Trails Tuman Race"], "2026-10-10", 1834, index)


def test_a_cyrillic_title_matches_its_latin_spelling():
    # Spelled from code points because this file may not carry non-ASCII literals: "Almaty" in
    # Cyrillic letters, which is how half the sources write it.
    almaty_cyrillic = "".join(chr(c) for c in (0x410, 0x43B, 0x43C, 0x430, 0x442, 0x44B))
    index = _index(_event("Almaty Marathon Race", "2026-09-20", city=3))
    assert matching_known([f"{almaty_cyrillic} Marathon Race"], "2026-09-20", 3, index)


def test_a_shared_rare_name_is_enough_on_its_own():
    """Event 480: "Etnoran.Chuvashia" and "Chuvashia Etnoran x Cheboksary Half" share one word.

    It is a word only two events on the site use, which says more than three common ones would.
    """
    known = _event("Chuvashia Etnoran x Cheboksary Half Marathon 2026", "2026-08-23", city=1768)
    index = _index(known, padded=True)
    assert matching_known(["Etnoran.Chuvashia Republic"], "2026-08-23", 1768, index)


def test_a_common_word_shared_by_many_events_is_not_evidence():
    """ "Marathon" is carried by 80 events here; sharing it must not make two of them one race."""
    index = build_index([_event(f"City{n} Marathon 2026", "2026-08-23", city=n) for n in range(_PADDING)])
    assert matching_known(["Some Other Marathon"], "2026-08-23", 500, index) is None


def test_the_same_series_in_two_cities_is_not_a_duplicate():
    """Events 31 and 32: Gran Fondo Russia in Tula and in Dubna, a day apart. Three words match."""
    index = _index(_event("Gran Fondo Russia - Tula 2026", "2026-07-25", city=101), padded=True)
    assert matching_known(["Gran Fondo Russia - Dubna 2026"], "2026-07-26", 102, index) is None


def test_a_weekly_ride_is_not_a_duplicate_of_last_week_s():
    """Identical titles seven days apart: the same ride happening again, not the same event."""
    index = _index(_event("Group ride from Nazarbayev 277A", "2026-05-23", city=3))
    assert matching_known(["Group ride from Nazarbayev 277A"], "2026-05-30", 3, index) is None


def test_a_date_written_a_day_out_still_matches():
    index = _index(_event("Zerenda Half Marathon 2026", "2026-10-03", city=1441))
    assert matching_known(["Zerenda Half Marathon"], "2026-10-04", 1441, index)


def test_an_unknown_city_does_not_block_a_match():
    """The place rules a duplicate out only when both sides have one; many candidates have none."""
    index = _index(_event("Zerenda Half Marathon 2026", "2026-10-03", city=1441))
    assert matching_known(["Zerenda Half Marathon"], "2026-10-03", None, index)


def test_the_match_names_the_event_it_found():
    index = _index(_event("Zerenda Half Marathon 2026", "2026-10-03"))
    assert matching_known(["Zerenda Half Marathon"], "2026-10-03", None, index) == "Zerenda Half Marathon 2026"


def test_any_locale_of_a_known_event_can_be_the_one_that_matches():
    index = _index(_event("Tuman", "2026-10-10", titles=["Tuman", "Fog Trail Race", "Tuman Zhalgas"]))
    assert matching_known(["Fog Trail Race 2026"], "2026-10-10", None, index) == "Tuman"


def test_a_single_shared_common_word_is_not_a_duplicate():
    # "Almaty" has to be common in the index for this to be the question it says it is.
    others = [_event(f"Almaty Ride {n}", "2020-01-01", city=3) for n in range(_PADDING)]
    index = build_index([_event("Almaty Criterium", "2026-07-01"), *others])
    assert matching_known(["Almaty Gran Fondo"], "2026-07-01", None, index) is None


def test_same_name_different_year_is_not_duplicate():
    index = _index(_event("Apricot Marathon Gravel MTB 2025", "2025-08-09"))
    assert matching_known(["Apricot Marathon Gravel MTB 2026"], "2026-08-09", None, index) is None


def test_too_few_meaningful_words_is_not_duplicate():
    index = _index(_event("Road Race extra words here", "2026-09-20"))
    assert matching_known(["Race"], "2026-09-20", None, index) is None


def test_an_accepted_event_joins_the_index_for_the_rest_of_the_run():
    index = _index()
    assert matching_known(["Zerenda Half Marathon"], "2026-10-03", None, index) is None
    index.add(_event("Zerenda Half Marathon 2026", "2026-10-03"))
    assert matching_known(["Zerenda Half Marathon"], "2026-10-03", None, index)


def test_rarity_is_ignored_until_the_calendar_is_big_enough_to_judge_it():
    """In a set of three events every word looks rare, which would make any shared word decisive."""
    index = _index(_event("Kodar Ridge Chara Sands", "2026-08-22", city=3462))
    assert matching_known(["Kodar Something Entirely Different"], "2026-08-22", 3462, index) is None
