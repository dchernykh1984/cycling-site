"""Check an uploaded photo and make the thumbnail the cards show; the photo itself is kept as it came.

The gallery holds the club's best shots, few of them and chosen by people who know what they upload,
so the original is stored byte for byte -- every pixel, the photographer's colour and sharpening, its
metadata too -- and served on the photo's own page and as the download. Only the card thumbnail is
made here: a page of forty cards must not pull forty full-size originals.

The file is still opened before it is accepted: that proves it is a picture a browser can show, and
refuses a decompression bomb before anything is decoded.
"""

from __future__ import annotations

import io
import uuid

from django.core.files.base import ContentFile
from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageOps, UnidentifiedImageError

#: Longest side of the card thumbnail; cards are at most ~560px wide, twice that for dense screens.
THUMB_SIDE = 1000
#: Below this a photo is not worth a card.
MIN_SIDE = 300
#: Decompression-bomb guard: a small file that unpacks into an enormous canvas.
MAX_PIXELS = 120_000_000
#: What a browser shows as it is, and the extension the stored original keeps.
FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}


class PhotoError(ValueError):
    """The upload cannot be used; the message is meant for the person uploading."""


def _thumbnail(uploaded) -> bytes:
    uploaded.seek(0)
    with Image.open(uploaded) as opened:
        # A JPEG can be decoded straight at a fraction of its size: a 50-megapixel original then
        # costs a few megabytes of memory here instead of a few hundred.
        opened.draft("RGB", (THUMB_SIDE, THUMB_SIDE))
        image = ImageOps.exif_transpose(opened) or opened
        if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
            rgba = image.convert("RGBA")
            flat = Image.new("RGB", rgba.size, (255, 255, 255))
            flat.paste(rgba, mask=rgba.split()[-1])
            image = flat
        else:
            image = image.convert("RGB")
        image.thumbnail((THUMB_SIDE, THUMB_SIDE), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85, optimize=True, progressive=True)
        return buffer.getvalue()


def process(uploaded) -> tuple[ContentFile, ContentFile]:
    """Return (original, thumbnail) ready for the two ImageFields, or raise PhotoError."""
    uploaded.seek(0)
    try:
        with Image.open(uploaded) as probe:  # reads the header only
            kind, size = probe.format, probe.size
    except Image.DecompressionBombError as exc:
        raise PhotoError(_("The image is too large to process.")) from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise PhotoError(_("This file is not an image we can read.")) from exc
    if kind not in FORMATS:
        raise PhotoError(_("This file is not an image we can read."))
    if size[0] * size[1] > MAX_PIXELS:
        raise PhotoError(_("The image is too large to process."))
    if max(size) < MIN_SIDE:
        raise PhotoError(_("The image is too small: at least %(size)d pixels on the longer side.") % {"size": MIN_SIDE})
    try:
        thumb = _thumbnail(uploaded)
    except (OSError, ValueError) as exc:  # a header that promised more than the file holds
        raise PhotoError(_("This file is not an image we can read.")) from exc

    uploaded.seek(0)
    stem = uuid.uuid4().hex[:16]
    original = ContentFile(uploaded.read(), name=f"{stem}.{FORMATS[kind]}")
    return original, ContentFile(thumb, name=f"{stem}.jpg")
