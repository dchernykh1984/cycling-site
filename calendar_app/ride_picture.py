"""The picture a chat shows for an event made from a virtual ride or race: the route's view in the virtual world
with the club's logo, and the event's day and time, title and route over it (specs/site/site-shell.md).

Each route's view is rendered from the trainer's scene once, beside its map (maps/<map>/views/<route>.jpg). The
logo and the type are a skin's, the one the settings name (RIDE_PICTURE_SKIN): its img/logo.png, and its fonts as its
stylesheet serves them -- a file per script, each for the characters its unicode-range lists. Without a view for the
route, or a skin without a logo and fonts, there is no picture and the event keeps the site's mark.
"""

from __future__ import annotations

import io
import re
from functools import cache
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1200, 630  # a chat's link card: 1.91 to 1
PAD = 48
LOGO = 150
SHADE_FROM = 0.4  # the dark under the words rises from this share of the height down
SHADE = 0.85
WHEN_PX, TITLE_PX, FACTS_PX, SMALLEST_PX = 64, 42, 30, 20
WHEN_WEIGHT, TITLE_WEIGHT, FACTS_WEIGHT = 800, 700, 500
#: A skin's fonts by their role (skin-<key>-heading, skin-<key>-body) and style, as its stylesheet names them.
HEADING, BODY = "heading", "body"
NORMAL, ITALIC = "normal", "italic"
#: The faces the picture draws with: its day and time in the heading's italic, its title and facts upright.
FACES = ((HEADING, NORMAL), (BODY, NORMAL), (HEADING, ITALIC))
WHITE, SOFT, ACCENT = (255, 255, 255), (235, 235, 235), (255, 140, 60)
QUALITY = 86
#: How long a line of the picture may be, as a draft brings it.
MAX_LINE = 120
_ROUTE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
_MAPS = Path(settings.BASE_DIR) / "trainer" / "static" / "trainer" / "alatau" / "maps"
_FACE = re.compile(r"@font-face\s*\{(?P<body>[^}]*)\}")


def view_of(route: str) -> Path | None:
    """The route's view in the virtual world, or None for a route without one."""
    if not _ROUTE.match(route or ""):
        return None
    return next(iter(sorted(_MAPS.glob(f"*/views/{route}.jpg"))), None)


@cache
def _faces(skin: str, role: str, style: str) -> tuple[tuple[Path, tuple[tuple[int, int], ...]], ...]:
    """The skin's font files for a role (heading, body) and a style, each with the characters it serves."""
    folder = Path(settings.BASE_DIR) / "skins" / skin
    css = folder / "skin.css"
    if not css.is_file():
        return ()
    out = []
    for face in _FACE.finditer(css.read_text(encoding="utf-8")):
        body = face["body"]
        family = re.search(r'font-family:\s*"([^"]+)"', body)
        italic = re.search(rf"font-style:\s*{ITALIC}", body) is not None
        src = re.search(r'src:\s*url\("([^"]+)"\)', body)
        ranges = re.search(r"unicode-range:\s*([^;]+);", body)
        if not (family and src and ranges) or family[1] != f"skin-{skin}-{role}" or italic != (style == ITALIC):
            continue
        spans = []
        for part in ranges[1].split(","):
            low, _, high = part.strip().removeprefix("U+").partition("-")
            spans.append((int(low, 16), int(high or low, 16)))
        out.append((folder / src[1], tuple(spans)))
    return tuple(out)


class _Type:
    """A skin's type at one size and weight: each character drawn from the file that serves it."""

    def __init__(self, skin: str, role: str, size: int, weight: int, style: str = NORMAL):
        self.size, self.fonts = size, []
        for path, spans in _faces(skin, role, style):
            font = ImageFont.truetype(str(path), size)
            if font.get_variation_axes():
                font.set_variation_by_axes([weight])
            self.fonts.append((font, spans))

    def font_for(self, ch: str):
        code = ord(ch)
        for font, spans in self.fonts:
            if any(low <= code <= high for low, high in spans):
                return font
        return self.fonts[0][0]

    def runs(self, text: str):
        """The text cut where its characters change file: (font, run)."""
        out: list[tuple[ImageFont.FreeTypeFont, str]] = []
        for ch in text:
            font = self.font_for(ch)
            if out and out[-1][0] is font:
                out[-1] = (font, out[-1][1] + ch)
            else:
                out.append((font, ch))
        return out

    def width(self, text: str) -> float:
        return sum(font.getlength(run) for font, run in self.runs(text))

    def draw(self, d: ImageDraw.ImageDraw, x: float, y: float, text: str, fill) -> None:
        for font, run in self.runs(text):
            d.text((x, y), run, font=font, fill=fill, anchor="ls")
            x += font.getlength(run)


def _fitted(skin: str, role: str, px: int, weight: int, text: str, room: int, style: str = NORMAL) -> _Type:
    """The type at px, or smaller down to SMALLEST_PX, so the line fits the room."""
    while True:
        kind = _Type(skin, role, px, weight, style)
        if px <= SMALLEST_PX or kind.width(text) <= room:
            return kind
        px -= 2


def _clean(line) -> str:
    return " ".join(str(line or "").split())[:MAX_LINE]


def draw(route: str, when: str, title: str, facts: str) -> bytes | None:
    """The event's picture as a JPEG, or None where the route has no view or the skin no logo or one of the faces it
    draws with (FACES: a skin without its heading's italic made a page fail, and with it the event being saved)."""
    view, skin = view_of(route), settings.RIDE_PICTURE_SKIN
    logo = Path(settings.BASE_DIR) / "skins" / skin / "img" / "logo.png"
    if view is None or not logo.is_file() or not all(_faces(skin, role, style) for role, style in FACES):
        return None
    when, title, facts = _clean(when), _clean(title), _clean(facts)
    picture = Image.open(view).convert("RGB").resize((WIDTH, HEIGHT))
    # the dark the words stand on, rising from the bottom
    shade = Image.new("L", (1, HEIGHT))
    top = int(HEIGHT * SHADE_FROM)
    for y in range(top, HEIGHT):
        shade.putpixel((0, y), int(255 * SHADE * ((y - top) / (HEIGHT - top)) ** 1.4))
    picture.paste(Image.new("RGB", (WIDTH, HEIGHT)), (0, 0), shade.resize((WIDTH, HEIGHT)))
    # the club's logo, its corners rounded
    mark = Image.open(logo).convert("RGB").resize((LOGO, LOGO), Image.Resampling.LANCZOS)
    round_mask = Image.new("L", (LOGO, LOGO))
    ImageDraw.Draw(round_mask).rounded_rectangle((0, 0, LOGO - 1, LOGO - 1), radius=LOGO // 7, fill=255)
    picture.paste(mark, (PAD, PAD), round_mask)
    # the day and time, the title, the route's length and climb: from the bottom up
    d, room = ImageDraw.Draw(picture), WIDTH - 2 * PAD
    y = HEIGHT - PAD
    if facts:
        _fitted(skin, BODY, FACTS_PX, FACTS_WEIGHT, facts, room).draw(d, PAD, y, facts, SOFT)
        y -= FACTS_PX + 22
    if title:
        _fitted(skin, HEADING, TITLE_PX, TITLE_WEIGHT, title, room).draw(d, PAD, y, title, ACCENT)
        y -= TITLE_PX + 24
    if when:
        _fitted(skin, HEADING, WHEN_PX, WHEN_WEIGHT, when, room, ITALIC).draw(d, PAD, y, when, WHITE)
    out = io.BytesIO()
    picture.save(out, "JPEG", quality=QUALITY, optimize=True, progressive=True)
    return out.getvalue()
