"""Pure fuzzy duplicate detection (no I/O, unit-tested).

The exact ``normalize_key`` (title + date) misses duplicates that mean the same event but are
worded differently -- extra words, another language variant, a dropped "(UCI)" etc. Here we compare
the *meaningful words* of titles, and pair that with the two other things the site knows about an
event: when it starts and which city it starts in.

Sources write the same race in ways no single comparison catches, so three signals are used and any
one of them is enough:

* the overlap of a title's words, as before;
* a shared *rare* word -- one that only a couple of events on the whole site use. "Marathon" says
  nothing (80 events carry it), "Etnoran" says almost everything (two do);
* words compared after transliteration and after merging neighbours, so "Open Band" matches
  "OpenBand" and a Cyrillic title matches its Latin spelling.

Two guards keep that from swallowing distinct races: the starts must be within a few days of each
other, and when both cities are known they must be the same one. Measured against the 15 duplicates
that were rejected by hand on this site, this catches 9 of them where the previous rule caught 5,
with no more false matches (12 pairs of genuinely distinct events, mostly a series' own stages and
the IRONSTAR/IRONLADY family, which read as duplicates to a person too).

A false match is the expensive kind of mistake -- the event is dropped and nobody sees it -- so
``matching_known`` hands back the event it matched, letting the run name it in the log instead of
reporting an anonymous "near-duplicate".
"""

from __future__ import annotations

import datetime
import itertools
import re
from collections import Counter
from dataclasses import dataclass, field

_WS = re.compile(r"\s+")
_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)

# English articles / prepositions / conjunctions that add no identity to an event name. Russian
# stop-words are intentionally not listed (that would put non-ASCII in the source); the overlap
# coefficient's min() denominator plus the min-shared-words and date guards already keep short
# Russian prepositions from inflating a match.
_STOPWORDS = frozenset({"the", "of", "a", "an", "and", "for", "to", "in", "on", "at"})

# Cyrillic (Russian + Kazakh) to Latin, so one spelling of a name matches the other. Sources give
# the same race in Cyrillic and in Latin letters, and the site stores a title in three locales that
# are often the same Russian text -- without this the locale variants add nothing to the comparison.
# Built from code points because this file may not carry non-ASCII literals: U+0430..U+044F is the
# lower-case Russian alphabet in order, followed by yo and the Kazakh letters.
_RUSSIAN_LATIN = "a b v g d e zh z i y k l m n o p r s t u f kh ts ch sh shch _ y _ e yu ya".replace("_", "").split(" ")
_TRANSLIT = {chr(0x430 + i): latin for i, latin in enumerate(_RUSSIAN_LATIN)}
_TRANSLIT[chr(0x451)] = "e"  # yo
_TRANSLIT.update(
    {
        chr(0x4D9): "a",  # ae
        chr(0x493): "g",  # ghain
        chr(0x49B): "k",  # qa
        chr(0x4A3): "n",  # eng
        chr(0x4E9): "o",  # oe
        chr(0x4B1): "u",  # straight u
        chr(0x4AF): "u",  # straight u with stroke
        chr(0x4BB): "h",  # shha
        chr(0x456): "i",  # dotted i
    }
)

# A word this site uses in at most this many events is a name rather than vocabulary, so sharing it
# is evidence on its own. Raising it costs precision fast: at 3 the false matches more than double.
_RARE_MAX_EVENTS = 2
_MIN_RARE_LENGTH = 3  # "5k", "ii" and the like are not names
# Rarity is a statement about a calendar, and a handful of events cannot support one: in a set of
# three, every word looks rare and any shared word would rule a duplicate. Below this many known
# events the word counts are ignored and only the title overlap decides.
_MIN_EVENTS_FOR_RARITY = 30

# Starts this far apart can still be the same race written with the wrong date; further apart and a
# weekly ride or a series' next stage starts reading as a duplicate of the one before it.
_WINDOW_DAYS = 3


def latin(text: str) -> str:
    return "".join(_TRANSLIT.get(ch, ch) for ch in text)


def _words(title: str) -> list[str]:
    """Meaningful lower-case words of a title, transliterated; year and punctuation dropped."""
    text = _PUNCT.sub(" ", _YEAR.sub(" ", (title or "").lower()))
    return [latin(word) for word in _WS.sub(" ", text).strip().split() if word and word not in _STOPWORDS]


def title_tokens(title: str) -> set[str]:
    """The distinct words of a title -- what its identity is compared on."""
    return set(_words(title))


def _with_merged_neighbours(title: str) -> set[str]:
    """Title words plus every neighbouring pair joined, so "Open Band" also reads as "OpenBand"."""
    words = _words(title)
    return set(words) | {first + second for first, second in itertools.pairwise(words)}


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


@dataclass(frozen=True)
class KnownTitle:
    """One localized title of an event the site already knows, prepared for comparison."""

    tokens: frozenset[str]
    merged: frozenset[str]  # tokens plus neighbouring pairs joined
    date_start: str
    city_id: int | None
    title: str  # the readable title, so a match can be named in the log


@dataclass
class KnownIndex:
    """Every known title, plus how many events use each word (rarity is what makes a word evidence)."""

    entries: list[KnownTitle] = field(default_factory=list)
    word_events: Counter = field(default_factory=Counter)
    events: int = 0

    def is_rare(self, word: str) -> bool:
        if self.events < _MIN_EVENTS_FOR_RARITY:
            return False
        return len(word) >= _MIN_RARE_LENGTH and 0 < self.word_events[word] <= _RARE_MAX_EVENTS

    def add(self, event: dict) -> None:
        """Fold an event the run just accepted into the index, so it is known from now on."""
        _index_event(self, event)


def _index_event(index: KnownIndex, event: dict) -> None:
    titles = [title for title in (event.get("titles") or [event.get("title", "")]) if title]
    date_start, city_id = event.get("date_start", ""), event.get("city_id")
    for title in titles:
        index.entries.append(
            KnownTitle(
                tokens=frozenset(title_tokens(title)),
                merged=frozenset(_with_merged_neighbours(title)),
                date_start=date_start,
                city_id=city_id,
                title=event.get("title") or title,
            )
        )
    # Rarity counts *events*, not titles: three locales of one name must not make it common.
    index.word_events.update({word for title in titles for word in title_tokens(title)})
    index.events += 1


def build_index(events) -> KnownIndex:
    """Index known events for matching. Each is a dict with ``titles``/``title``, ``date_start``
    and an optional ``city_id``; one entry per localized title so a Russian proposal can match the
    English spelling already on the site."""
    index = KnownIndex()
    for event in events:
        _index_event(index, event)
    return index


def _same_place(a: int | None, b: int | None) -> bool:
    """Whether two events may be in the same place. Unknown on either side means "cannot tell"."""
    return a is None or b is None or a == b


def _looks_like(
    tokens: set[str], merged: set[str], known: KnownTitle, index: KnownIndex, threshold: float, min_shared: int
) -> bool:
    if len(tokens) < min_shared or len(known.tokens) < min_shared:
        return False
    if any(index.is_rare(word) for word in tokens & known.tokens):
        return True
    # Merged neighbours may create a match but must not inflate the score, so the coefficient is
    # still measured against the titles' own words.
    shared = (merged & known.tokens) | (tokens & known.merged)
    return len(shared) >= min_shared and len(shared) / min(len(tokens), len(known.tokens)) >= threshold


def matching_known(
    titles: list[str],
    date_start: str,
    city_id: int | None,
    index: KnownIndex,
    *,
    threshold: float = 0.7,
    min_shared: int = 2,
    window_days: int = _WINDOW_DAYS,
) -> str | None:
    """The known event this one duplicates, or None. Any localized title may be the one that matches."""
    # Read once, not once per known title: a run compares every candidate against the site's whole
    # calendar, so tokenizing inside that loop would repeat the same work thousands of times.
    prepared = [(title_tokens(title), _with_merged_neighbours(title)) for title in titles if title]
    for known in index.entries:
        if not _dates_close(date_start, known.date_start, window_days):
            continue
        if not _same_place(city_id, known.city_id):
            continue
        for tokens, merged in prepared:
            if _looks_like(tokens, merged, known, index, threshold, min_shared):
                return known.title
    return None
