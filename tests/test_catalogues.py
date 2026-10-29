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
