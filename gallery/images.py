"""Turn an uploaded photo into the two files the gallery serves.

Every upload is opened as an image and written out again, never stored as it came: that proves the
file is a picture, applies the camera's rotation, and drops the EXIF block -- a phone photo carries
where it was taken and on which device, and these files are public. Two sizes are kept: the photo
itself, bounded so a 50-megapixel original does not become a 20 MB download, and a thumbnail for the
cards, which is what most visitors ever load.
"""

from __future__ import annotations

import io
import uuid

from django.core.files.base import ContentFile
from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageOps, UnidentifiedImageError

#: Longest side of the stored photo: sharp on a large screen, a few hundred kilobytes as JPEG.
FULL_SIDE = 2400
#: Longest side of the card thumbnail; cards are at most ~560px wide, twice that for dense screens.
THUMB_SIDE = 1000
#: Below this a photo is not worth a card.
MIN_SIDE = 300
#: Decompression-bomb guard: a small file that unpacks into an enormous canvas.
MAX_PIXELS = 120_000_000


class PhotoError(ValueError):
    """The upload cannot be used; the message is meant for the person uploading."""


def _encode(image: Image.Image, side: int, quality: int) -> bytes:
    copy = image.copy()
    if max(copy.size) > side:
        copy.thumbnail((side, side), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    copy.save(buffer, format="JPEG", quality=quality, optimize=True, progressive=True)
    return buffer.getvalue()


def process(uploaded) -> tuple[ContentFile, ContentFile]:
    """Return (photo, thumbnail) as JPEG files ready for the two ImageFields, or raise PhotoError."""
    previous_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        uploaded.seek(0)
        try:
            opened = Image.open(uploaded)
            opened.load()
        except Image.DecompressionBombError as exc:
            raise PhotoError(_("The image is too large to process.")) from exc
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise PhotoError(_("This file is not an image we can read.")) from exc

        image: Image.Image = ImageOps.exif_transpose(opened) or opened
        if max(image.size) < MIN_SIDE:
            raise PhotoError(
                _("The image is too small: at least %(size)d pixels on the longer side.") % {"size": MIN_SIDE}
            )
        # Photos have no transparency worth keeping; flatten anything that has it onto white.
        if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
            rgba = image.convert("RGBA")
            flat = Image.new("RGB", rgba.size, (255, 255, 255))
            flat.paste(rgba, mask=rgba.split()[-1])
            image = flat
        else:
            image = image.convert("RGB")

        stem = uuid.uuid4().hex[:16]
        full = ContentFile(_encode(image, FULL_SIDE, 85), name=f"{stem}.jpg")
        thumb = ContentFile(_encode(image, THUMB_SIDE, 80), name=f"{stem}.jpg")
        return full, thumb
    finally:
        Image.MAX_IMAGE_PIXELS = previous_limit
