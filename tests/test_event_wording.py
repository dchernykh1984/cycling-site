"""The calendar is not only for races, so its wording must not promise one.

Each entry here was once "competition" in all three locales. Renaming a msgid is half a
change: miss the catalogue and the page quietly serves the English source to a Russian
reader, which no other test would notice. The list grows as the sweep goes on.
"""

from pathlib import Path

from django.test import SimpleTestCase
from django.utils.translation import gettext
from django.utils.translation import override as translation_override

# The em dash is escaped because source files in this repository are ASCII only.
RENAMED = (
    "Event",
    "Events",
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
    "Cannot delete a location that still has nested locations or events.",
    "This location cannot be rejected: approved locations or a published event are inside it.",
    "Events recently added to the Universal Bicycle Team calendar.",
    "Reject this venue? Events using it will fall back to the city's other location.",
    "Events by region",
    "Events by city",
    "Events by discipline",
    "No events found for the selected period.",
    "Your event was sent for review again.",
)


class EventWordingTests(SimpleTestCase):
    def test_every_renamed_string_is_translated(self):
        for msgid in RENAMED:
            for lang in ("ru", "kk"):
                with self.subTest(msgid=msgid, lang=lang), translation_override(lang):
                    self.assertNotEqual(gettext(msgid), msgid, "missing from the catalogue")


# "sorevnovanie" -- the Russian for a competition, escaped because sources here are ASCII only.
COMPETITION_RU = "\u0441\u043e\u0440\u0435\u0432\u043d\u043e\u0432\u0430\u043d"


class NoCompetitionWordingLeftTests(SimpleTestCase):
    def test_no_russian_string_calls_an_entry_a_competition(self):
        """The sweep above is only worth doing once; this keeps the word from drifting back.

        A real race is still a race, and an announcement written by an organizer may say so --
        that is content, which lives in model columns, not here. This covers the interface.
        """
        import polib
        from django.conf import settings

        path = Path(settings.BASE_DIR) / "cycling_site" / "locale" / "ru" / "LC_MESSAGES" / "django.po"
        offenders = [e.msgid for e in polib.pofile(str(path)) if not e.obsolete and COMPETITION_RU in e.msgstr.lower()]
        self.assertEqual(offenders, [])
