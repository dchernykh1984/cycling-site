"""What a catalogue's translation must keep, checked over every entry of every locale.

A reader cannot see a Latin letter inside a Cyrillic word, but search and sorting can; a letter typed
three times is a slip; and a translation that loses a placeholder or a tag breaks the page it is on.
"""

import re
from pathlib import Path

import pytest

LOCALE = Path(__file__).resolve().parent.parent / "cycling_site" / "locale"
CYRILLIC = re.compile(f"[{chr(0x0400)}-{chr(0x04FF)}]")
LATIN = re.compile("[A-Za-z]")
NOT_WORDS = re.compile(r"%\(\w+\)[sd]|%[sd]|<[^>]+>|&\w+;|\{\w+\}|https?://\S+")
PLACEHOLDER = re.compile(r"%\(\w+\)[sd]|%[sd]|\{\w+\}")
TAG = re.compile(r"</?(\w+)")


def _joined(block: str, key: str) -> str | None:
    found = re.search(rf'^{key} ((?:".*"\n?)+)', block, re.M)
    return "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', found.group(1))) if found else None


def _entries(language: str) -> list[tuple[str, str]]:
    text = (LOCALE / language / "LC_MESSAGES" / "django.po").read_text(encoding="utf-8")
    pairs = [(_joined(block, "msgid"), _joined(block, "msgstr")) for block in text.split("\n\n")]
    return [(msgid, msgstr) for msgid, msgstr in pairs if msgid and msgstr]


LANGUAGES = sorted(path.name for path in LOCALE.iterdir() if (path / "LC_MESSAGES" / "django.po").exists())


@pytest.mark.parametrize("language", LANGUAGES)
def test_no_word_mixes_latin_and_cyrillic_letters(language):
    mixed = [
        word
        for _msgid, msgstr in _entries(language)
        for word in re.findall(r"[^\W\d_]+", NOT_WORDS.sub(" ", msgstr))
        if CYRILLIC.search(word) and LATIN.search(word)
    ]
    assert mixed == []


@pytest.mark.parametrize("language", LANGUAGES)
def test_no_letter_is_typed_three_times(language):
    tripled = [
        word
        for _msgid, msgstr in _entries(language)
        for word in re.findall(r"[^\W\d_]+", NOT_WORDS.sub(" ", msgstr))
        if re.search(r"(\w)\1\1", word)
    ]
    assert tripled == []


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_translation_keeps_its_placeholders_and_tags(language):
    lost = [
        msgid
        for msgid, msgstr in _entries(language)
        if sorted(PLACEHOLDER.findall(msgid)) != sorted(PLACEHOLDER.findall(msgstr))
        or sorted(TAG.findall(msgid)) != sorted(TAG.findall(msgstr))
    ]
    assert lost == []


def test_the_russian_catalogue_calls_an_event_one_thing():
    # The calendar's events are "meropriyatiya" in Russian everywhere: menus, buttons, moderation.
    # "Sobytiya" (occurrences) is kept only for the gallery's "our events & moments", a matter of life.
    occurrence = "".join(chr(code) for code in (0x0441, 0x043E, 0x0431, 0x044B, 0x0442))
    found = [msgid for msgid, msgstr in _entries("ru") if occurrence in msgstr.lower()]
    assert found == ["our events & moments"]


def _word(*codes: int) -> str:
    return "".join(chr(code) for code in codes)


def test_the_kazakh_catalogue_names_a_region_and_an_event_one_way():
    # A region is "aimaq" everywhere, never "olke" or "onir"; an event is "is-shara", and "oqiga" (a
    # happening) is kept only where the English speaks of stories or moments.
    olke, onir = _word(0x04E9, 0x043B, 0x043A, 0x0435), _word(0x04E9, 0x04A3, 0x0456, 0x0440)
    happening = _word(0x043E, 0x049B, 0x0438, 0x0493, 0x0430)
    entries = _entries("kk")
    assert [msgid for msgid, msgstr in entries if olke in msgstr.lower() or onir in msgstr.lower()] == []
    assert sorted(msgid for msgid, msgstr in entries if happening in msgstr.lower()) == [
        "Announcements, results and stories from the Universal Bicycle Team calendar.",
        "our events & moments",
    ]
