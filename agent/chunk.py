"""Split a long aggregator page into smaller pieces so the model enumerates every row.

Aggregator/calendar text is fetched line-structured (one race per line). A very long, dense list is
easier for the model to read exhaustively in several smaller passes than in one big prompt -- at
temperature 0 a single pass deterministically drops the same terse rows every run. These helpers are
pure (no I/O) and unit-tested; agent.run feeds each chunk to the extractor and merges the resulting
candidates (the pipeline dedups downstream, so a race repeated across chunks is harmless).
"""

from __future__ import annotations

from agent.links import LINKS_MARKER as _LINKS_MARKER


def split_text(text: str, max_chars: int) -> list[str]:
    """Split ``text`` into pieces of at most ``max_chars``, breaking only at line boundaries.

    A single line longer than ``max_chars`` is kept whole in its own (over-long) chunk rather than
    cut mid-row. Returns ``[text]`` when it already fits. Joining the pieces reproduces ``text``.
    """
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.splitlines(keepends=True):
        if current and size + len(line) > max_chars:
            chunks.append("".join(current))
            current, size = [], 0
        current.append(line)
        size += len(line)
    if current:
        chunks.append("".join(current))
    return chunks


def split_source_text(text: str, max_chars: int) -> list[str]:
    """Chunk a fetched aggregator text, repeating its 'Links on the page' block in every chunk.

    The readable body is split on line boundaries; the trailing link list (which any race may need to
    resolve its source_url) is appended to each chunk, so no chunk loses the links.
    """
    body, marker, links = text.partition(_LINKS_MARKER)
    tail = marker + links if marker else ""
    return [piece + tail for piece in split_text(body, max_chars)]
