from agent.dedup import is_duplicate, matches_known, title_tokens


def _known(title, date):
    return (title_tokens(title), date)


def test_title_tokens_drops_year_punctuation_and_stopwords():
    assert title_tokens("Apricot Marathon - Gravel & MTB 2026") == {"apricot", "marathon", "gravel", "mtb"}
    assert title_tokens("Championship of Kyrgyzstan on the road 2025") == {"championship", "kyrgyzstan", "road"}


def test_verbose_retitling_same_date_is_duplicate():
    # Mirrors "Apricot Marathon Gravel & MTB Race 2026" vs "Apricot Marathon - Gravel & MTB 2026".
    known = [_known("Apricot Marathon Gravel MTB 2026", "2026-08-09")]
    assert matches_known(["Apricot Marathon Gravel MTB Race 2026"], "2026-08-09", known) is True


def test_extra_words_but_shared_core_same_date_is_duplicate():
    # Mirrors the Kyrgyzstan championship: extra "cycling / amateurs / masters" vs "(UCI)".
    known = [_known("Championship Kyrgyzstan road 2026 UCI", "2026-08-15")]
    cand = "Championship Kyrgyzstan road cycling 2026 amateurs masters"
    assert matches_known([cand], "2026-08-15", known) is True


def test_cross_language_duplicate_matches_via_english_variant():
    # An existing event stored only in English; the ru proposal does not match, but its en
    # translation does -- so it is still caught (mirrors ru event 292 vs en event 40).
    known = [_known("Apricot Marathon Gravel MTB 2026", "2026-08-09")]
    variants = ["Aprikot Marafon 2026", "", "Apricot Marathon Gravel MTB Race 2026"]  # ru, kk, en
    assert matches_known(variants, "2026-08-09", known) is True


def test_only_generic_words_shared_is_not_duplicate():
    known = [_known("Road Race autumn ITT road MTB run 10 km duathlon", "2026-09-20")]
    assert matches_known(["Road Race highway ride relay"], "2026-09-20", known) is False


def test_single_shared_word_is_not_duplicate():
    known = [_known("Almaty Criterium", "2026-07-01")]
    assert matches_known(["Almaty Gran Fondo"], "2026-07-01", known) is False  # only "almaty" in common


def test_same_name_different_year_is_not_duplicate():
    known = [_known("Apricot Marathon Gravel MTB 2025", "2025-08-09")]
    assert matches_known(["Apricot Marathon Gravel MTB 2026"], "2026-08-09", known) is False  # dates far apart


def test_close_date_within_window_still_matches():
    known = [_known("Apricot Marathon Gravel MTB", "2026-08-09")]
    assert matches_known(["Apricot Marathon Gravel MTB Race"], "2026-08-12", known) is True  # 3 days apart


def test_too_few_meaningful_words_is_not_duplicate():
    known = [_known("Road Race extra words here", "2026-09-20")]
    assert is_duplicate(title_tokens("Race"), "2026-09-20", known) is False  # candidate has < 2 tokens
