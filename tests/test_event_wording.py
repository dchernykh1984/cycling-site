"""The calendar is not only for races, so its wording must not promise one.

Each entry here was once "competition" in all three locales. Renaming a msgid is half a
change: miss the catalogue and the page quietly serves the English source to a Russian
reader, which no other test would notice. The list grows as the sweep goes on.
"""

from django.test import SimpleTestCase
from django.utils.translation import gettext
from django.utils.translation import override as translation_override

RENAMED = (
    "Submit event",
    "Event list",
    "All events as a list",
    "Nearest events",
    "New events (RSS)",
    "New events",
)


class EventWordingTests(SimpleTestCase):
    def test_every_renamed_string_is_translated(self):
        for msgid in RENAMED:
            for lang in ("ru", "kk"):
                with self.subTest(msgid=msgid, lang=lang), translation_override(lang):
                    self.assertNotEqual(gettext(msgid), msgid, "missing from the catalogue")
