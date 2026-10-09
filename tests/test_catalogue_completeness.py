"""Guards for the two ways a translation goes missing without anybody noticing.

Both bit this repository at once. Five strings added with the link-preview image never
reached the catalogues, because nothing ran ``makemessages`` after that change; and five
entries sat marked ``fuzzy`` holding the translation of a different string entirely
("Add email" against "Dobavit' stat'yu"). gettext answers with the English source in both
cases, so the page still renders and no test ever fails -- it just stops being Russian.
"""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.utils.translation import gettext
from django.utils.translation import override as translation_override

LOCALES = ("ru", "kk")

# Added with the link-preview image and missed by the catalogues until this was written.
PREVIEW_IMAGE_STRINGS = (
    "The image is too large to process.",
    "This file is not an image we can read.",
    "The image is too small: at least %(size)d pixels on the longer side.",
    "Link preview image",
    "Shown when somebody pastes a link to this event into a chat. Upload it before the "
    "link goes round: messengers remember the first picture they saw for a long time.",
)


def _catalogue(locale: str) -> Path:
    return Path(settings.BASE_DIR) / "cycling_site" / "locale" / locale / "LC_MESSAGES" / "django.po"


class CatalogueCompletenessTests(SimpleTestCase):
    def test_no_entry_is_left_untranslated(self):
        import polib

        for locale in LOCALES:
            with self.subTest(locale=locale):
                missing = [
                    e.msgid
                    for e in polib.pofile(str(_catalogue(locale)))
                    if not e.obsolete and not e.msgstr and not e.msgstr_plural
                ]
                self.assertEqual(missing, [], "these would render in English")

    def test_no_entry_is_marked_fuzzy(self):
        """A fuzzy entry is ignored at runtime and usually holds a translation of something else."""
        import polib

        for locale in LOCALES:
            with self.subTest(locale=locale):
                fuzzy = [
                    e.msgid for e in polib.pofile(str(_catalogue(locale))) if not e.obsolete and "fuzzy" in e.flags
                ]
                self.assertEqual(fuzzy, [])

    def test_the_link_preview_strings_reach_the_reader(self):
        for msgid in PREVIEW_IMAGE_STRINGS:
            for locale in LOCALES:
                with self.subTest(msgid=msgid, locale=locale), translation_override(locale):
                    self.assertNotEqual(gettext(msgid), msgid)
