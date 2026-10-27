"""Opt-in, read-only storage contract check. Credentials and fixture link are CI secrets."""

import hashlib
import os
from io import BytesIO

import pytest
from PIL import Image

from event_photos.dropbox import DropboxAdapter, DropboxError, is_folder_link
from event_photos.index import IndexValidationError, parse
from event_photos.models import THUMBNAIL_LIMIT_BYTES


@pytest.mark.skipif(os.environ.get("RUN_DROPBOX_INTEGRATION") != "1", reason="live Dropbox check is opt-in")
def test_a_shared_album_supplies_a_valid_index_and_a_real_thumbnail(settings):
    folder = os.environ.get("DROPBOX_TEST_FOLDER_URL", "")
    if not is_folder_link(folder):
        pytest.fail("DROPBOX_TEST_FOLDER_URL must be a shared folder containing photo-index.v1.json")
    if not settings.DROPBOX_APP_KEY or not settings.DROPBOX_APP_SECRET:
        pytest.fail("DROPBOX_APP_KEY and DROPBOX_APP_SECRET are required")
    adapter = DropboxAdapter()
    try:
        raw = adapter.read_file(folder, "photo-index.v1.json")
        index = parse(raw, hashlib.sha256(raw).hexdigest())
        usable = next((p for p in index.photos if p.preview_path or p.original_bytes <= THUMBNAIL_LIMIT_BYTES), None)
        if usable is None:
            pytest.fail("The fixture needs at least one photo with a usable preview")
        data = adapter.thumbnail(folder, usable.preview_path or usable.original_path)
    except DropboxError as exc:
        pytest.fail(f"Dropbox storage check failed: {exc.kind}", pytrace=False)
    except IndexValidationError:
        pytest.fail("Dropbox returned an invalid photo index", pytrace=False)
    with Image.open(BytesIO(data)) as image:
        assert image.format == "JPEG"
        assert 0 < image.width <= 256 and 0 < image.height <= 256
        image.load()
