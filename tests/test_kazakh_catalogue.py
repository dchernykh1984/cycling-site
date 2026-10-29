"""The Kazakh catalogue is written in Kazakh letters.

Some of its words were typed with Russian letters standing in for the Kazakh ones, or with a Latin
"i" for the Kazakh one -- "log out" with a plain Russian g where the Kazakh "gh" belongs. Each word put
right is pinned here by the letters it must carry. The source is ASCII-only, so the letters are
built from their code points.
"""

from django.test import SimpleTestCase
from django.utils import translation
from django.utils.translation import gettext

AE, GH, Q, NG, OE, UU, UE, KZ_I = (
    chr(code) for code in (0x04D9, 0x0493, 0x049B, 0x04A3, 0x04E9, 0x04B1, 0x04AF, 0x0456)
)

# msgid -> the Kazakh letters its translation must hold.
PINNED = {
    "Resend confirmation email": (Q, KZ_I),
    "Role": (OE,),
    "Appearance": (OE, KZ_I),
    "Theme": (Q,),
    "My submissions": (NG, KZ_I),
    "API access": (KZ_I,),
    "Use this token to authenticate API requests: <code>Authorization: Bearer &lt;token&gt;</code>": (
        UU,
        UE,
        KZ_I,
        NG,
    ),
    "No token yet. Generate one below.": (AE, Q, OE, NG),
    "Regenerate token": (KZ_I, NG),
    "API docs (Swagger)": (UU,),
    "Log out": (GH,),
}


class KazakhLettersTests(SimpleTestCase):
    def test_each_word_put_right_keeps_its_kazakh_letters(self):
        with translation.override("kk"):
            for msgid, letters in PINNED.items():
                text = gettext(msgid)
                for letter in letters:
                    with self.subTest(msgid=msgid[:40], letter=f"U+{ord(letter):04X}"):
                        self.assertIn(letter, text)
