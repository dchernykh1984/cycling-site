"""One rule for matching typed text, whatever the script: the gallery's event picker and the
protocol search both fold text to lower-case Latin words, so "Che" finds "Chernykh" whichever
script either was typed in.
"""

from __future__ import annotations

import re
from functools import lru_cache

from anyascii import anyascii

#: Letters a browser has to fold itself: Latin with diacritics and Cyrillic (Kazakh included).
_FOLDED_RANGES = ((0x00C0, 0x024F), (0x0400, 0x04FF))


def search_words(value: str) -> list[str]:
    """One script and case for matching, including a mixture of Cyrillic and Latin letters."""
    return re.findall(r"[a-z0-9]+", anyascii(value).casefold())


@lru_cache(maxsize=1)
def fold_table() -> dict[str, str]:
    """What search_words does to each letter, for a page that folds a query in the browser."""
    table = {}
    for start, end in _FOLDED_RANGES:
        for code in range(start, end + 1):
            letter = chr(code)
            folded = anyascii(letter).casefold()
            if folded != letter.casefold():
                table[letter] = folded
    return table
