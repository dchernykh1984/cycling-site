"""Turn whatever somebody uploads into a picture a chat can show.

An event's preview image is the one file on this site that is fetched by machines we do not
control -- Telegram, WhatsApp and the rest read it off the page when a link is pasted. So nothing
is taken on trust: the bytes are opened as an image before anything else, bounded, and written out
again. Re-encoding is the point rather than a side effect. It settles three things at once:

* the file really is an image, not a renamed archive with an image's extension;
* no camera metadata survives -- a phone photo carries the place it was taken and the device that
  took it, and this file is public;
* the dimensions are known, so the page can declare them and a messenger can lay out the card
  without downloading anything.

Oversized uploads are scaled down rather than refused: a poster exported at 4000px is a normal
thing to be handed, and shrinking it is not a decision the person uploading needs to make.
"""

from __future__ import annotations

import io

from django.core.files.base import ContentFile
from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageOps, UnidentifiedImageError

#: Longest side of what is stored. Large enough for any chat card, small enough that the file
#: stays a few hundred kilobytes; a messenger downloads this before it can draw anything.
MAX_SIDE = 1200

#: Below this a preview is not worth having: most platforms ignore an image this small and show
#: their own placeholder instead, which looks like a bug rather than a choice.
MIN_SIDE = 200

#: A guard against a decompression bomb -- a small file that unpacks into an enormous canvas.
#: Pillow's own default is far higher than anything a race poster needs.
MAX_PIXELS = 50_000_000


class PreviewImageError(ValueError):
    """The upload cannot be used as a preview; the message is meant for the person uploading."""


def normalise(uploaded) -> tuple[ContentFile, int, int]:
    """Return (file, width, height) ready to store, or raise PreviewImageError.

    The caller gets a file it can assign straight to an ImageField.
    """
    previous_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        uploaded.seek(0)
        try:
            opened = Image.open(uploaded)
            opened.load()
        except Image.DecompressionBombError as exc:
            raise PreviewImageError(_("The image is too large to process.")) from exc
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise PreviewImageError(_("This file is not an image we can read.")) from exc

        # A photo taken sideways carries its rotation in EXIF; apply it now, because the tag is
        # about to be dropped along with the rest of the metadata.
        image: Image.Image = ImageOps.exif_transpose(opened) or opened

        if max(image.size) < MIN_SIDE:
            raise PreviewImageError(
                _("The image is too small: at least %(size)d pixels on the longer side.") % {"size": MIN_SIDE}
            )

        # RGBA and LA carry alpha in the mode itself; a palette image carries it in a tag. The
        # first spelling is the one a logo exported from a design tool actually arrives in.
        keeps_transparency = image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)
        image = image.convert("RGBA" if keeps_transparency else "RGB")

        if max(image.size) > MAX_SIDE:
            # thumbnail() keeps the aspect ratio, so neither side can exceed the bound.
            image.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        if keeps_transparency:
            image.save(buffer, format="PNG", optimize=True)
            name = "preview.png"
        else:
            image.save(buffer, format="JPEG", quality=85, optimize=True, progressive=True)
            name = "preview.jpg"
        width, height = image.size
        return ContentFile(buffer.getvalue(), name=name), width, height
    finally:
        Image.MAX_IMAGE_PIXELS = previous_limit
