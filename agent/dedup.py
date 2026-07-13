"""Pure fuzzy duplicate detection (no I/O, unit-tested).

The exact ``normalize_key`` (title + date) misses duplicates that mean the same event but are
worded differently -- extra words, another language variant, a dropped "(UCI)" etc. Here we compare
the *meaningful words* of two titles with an overlap coefficient and require the dates to be close,
so a verbose re-titling of the same race on the same day is caught while a different race, or the
same series in a different year, is not.
"""

from __future__ import annotations

import datetime
import re

_WS = re.compile(r"\s+")
_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)

# English articles / prepositions / conjunctions that add no identity to an event name. Russian
# stop-words are intentionally not listed (that would put non-ASCII in the source); the overlap
# coefficient's min() denominator plus the min-shared-words and date guards already keep short
# Russian prepositions from inflating a match.
_STOPWORDS = frozenset({"the", "of", "a", "an", "and", "for", "to", "in", "on", "at"})


def title_tokens(title: str) -> set[str]:
    """Meaningful lower-case word tokens of a title: year and punctuation dropped, stopwords removed."""
    text = _YEAR.sub(" ", (title or "").lower())
    text = _PUNCT.sub(" ", text)
    return {tok for tok in _WS.sub(" ", text).strip().split() if tok and tok not in _STOPWORDS}


def _overlap(a: set[str], b: set[str]) -> float:
    """Overlap coefficient |a n b| / min(|a|,|b|) -- high when one title's words contain the other's."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def _dates_close(a: str, b: str, window_days: int) -> bool:
    try:
        da = datetime.date.fromisoformat((a or "")[:10])
        db = datetime.date.fromisoformat((b or "")[:10])
    except ValueError:
        return False
    return abs((da - db).days) <= window_days


def is_duplicate(
    title: str,
    date_start: str,
    known: list[tuple[set[str], str]],
    *,
    threshold: float = 0.7,
    min_shared: int = 2,
    window_days: int = 7,
) -> bool:
    """Whether ``(title, date_start)`` is a near-duplicate of any known ``(tokens, date)`` pair.

    A duplicate must share at least ``min_shared`` meaningful words, reach ``threshold`` overlap and
    fall within ``window_days`` of the known date. Requiring several shared words plus a close date
    keeps a single common word (e.g. a city name) or a different year's edition from matching.
    """
    tokens = title_tokens(title)
    if len(tokens) < min_shared:
        return False
    for known_tokens, known_date in known:
        if (
            len(tokens & known_tokens) >= min_shared
            and _overlap(tokens, known_tokens) >= threshold
            and _dates_close(date_start, known_date, window_days)
        ):
            return True
    return False
