"""What the normaliser does with what people actually upload."""

import io

from django.test import SimpleTestCase
from PIL import Image

from calendar_app.preview_image import MAX_SIDE, MIN_SIDE, PreviewImageError, normalise


def _upload(size, mode="RGB", fmt="PNG", **info):
    buffer = io.BytesIO()
    Image.new(mode, size, "red").save(buffer, format=fmt, **info)
    buffer.seek(0)
    buffer.name = f"poster.{fmt.lower()}"
    return buffer


class NormaliseTests(SimpleTestCase):
    def test_an_ordinary_poster_is_kept_at_its_own_size(self):
        _, width, height = normalise(_upload((800, 600)))
        assert (width, height) == (800, 600)

    def test_something_enormous_is_scaled_down_keeping_its_shape(self):
        """A poster exported at 4000px is a normal thing to be handed; shrink it, do not refuse it."""
        _, width, height = normalise(_upload((4000, 2000)))
        assert max(width, height) == MAX_SIDE
        assert width / height == 2.0, f"the shape changed: {width}x{height}"

    def test_a_tall_poster_is_bounded_on_its_long_side_too(self):
        _, width, height = normalise(_upload((1000, 3000)))
        assert max(width, height) == MAX_SIDE
        assert width < height

    def test_something_too_small_to_be_shown_is_refused(self):
        with self.assertRaises(PreviewImageError):
            normalise(_upload((MIN_SIDE - 50, MIN_SIDE - 50)))

    def test_a_file_that_is_not_an_image_is_refused(self):
        payload = io.BytesIO(b"PK\x03\x04 this is a zip wearing a png name")
        payload.name = "poster.png"
        with self.assertRaises(PreviewImageError):
            normalise(payload)

    def test_transparency_survives_as_png(self):
        """A logo on a transparent background must not gain a black box behind it."""
        transparent = Image.new("RGBA", (400, 400), (255, 0, 0, 0))
        buffer = io.BytesIO()
        transparent.save(buffer, format="PNG")
        buffer.seek(0)
        buffer.name = "logo.png"
        stored, _, _ = normalise(buffer)
        assert stored.name.endswith(".png")
        assert Image.open(io.BytesIO(stored.read())).mode == "RGBA"

    def test_a_photo_comes_back_as_jpeg(self):
        stored, _, _ = normalise(_upload((900, 900), fmt="JPEG"))
        assert stored.name.endswith(".jpg")

    def test_camera_metadata_does_not_survive(self):
        """This file is public; a phone photo carries where it was taken and on what."""
        source = Image.new("RGB", (600, 400), "blue")
        buffer = io.BytesIO()
        exif = source.getexif()
        exif[271] = "SecretPhoneMaker"  # Make
        source.save(buffer, format="JPEG", exif=exif)
        buffer.seek(0)
        buffer.name = "photo.jpg"
        stored, _, _ = normalise(buffer)
        assert b"SecretPhoneMaker" not in stored.read()

    def test_the_stored_size_is_what_the_page_will_declare(self):
        stored, width, height = normalise(_upload((1500, 500)))
        reopened = Image.open(io.BytesIO(stored.read()))
        assert reopened.size == (width, height)
