"""The calendar is not only for races, so its wording must not promise one.

Each entry here was once "competition" in all three locales. Renaming a msgid is half a
change: miss the catalogue and the page quietly serves the English source to a Russian
reader, which no other test would notice. The list grows as the sweep goes on.
"""

from django.test import SimpleTestCase
from django.utils.translation import gettext
from django.utils.translation import override as translation_override

# The em dash is escaped because source files in this repository are ASCII only.
RENAMED = (
    "Submit event",
    "Event list",
    "All events as a list",
    "Nearest events",
    "New events (RSS)",
    "New events",
    "Event moderation",
    "No events pending approval.",
    "This event is hidden from public view.",
    "Are you sure you want to delete this event?",
    "Delete this event?",
    "Prefilled when you register for an event.",
    "Choose one or more disciplines \u2014 an event can belong to several.",
    "Only a rejected event can be resubmitted.",
    "Prefilled into the registration field for events that collect Strava links.",
    "Reject this place? Everything nested inside it is removed too, and events there lose their location.",
    "Timing token deleted. Timing tools can no longer access this event.",
    "This location has nested locations or events, so its level cannot be changed.",
)


class EventWordingTests(SimpleTestCase):
    def test_every_renamed_string_is_translated(self):
        for msgid in RENAMED:
            for lang in ("ru", "kk"):
                with self.subTest(msgid=msgid, lang=lang), translation_override(lang):
                    self.assertNotEqual(gettext(msgid), msgid, "missing from the catalogue")
