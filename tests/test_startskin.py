"""manage.py startskin: a new skin's folder that the registry accepts as it is."""

import io
import pathlib
import tempfile

import pytest
from django.core.management import CommandError, call_command
from django.test import override_settings

from cycling_site import skins


@pytest.fixture
def skins_dir():
    root = pathlib.Path(tempfile.mkdtemp())
    with override_settings(SKINS_DIR=root):
        skins.registry.cache_clear()
        yield root
    skins.registry.cache_clear()


def test_the_new_folder_is_a_valid_skin_on_the_chosen_mode(skins_dir):
    out = io.StringIO()
    call_command("startskin", "ubt", "--mode", "dark", stdout=out)
    skin = skins._load(skins_dir / "ubt")
    assert (skin.key, skin.mode, skin.order) == ("ubt", "dark", 10)
    assert ':root[data-skin="ubt"]' in (skins_dir / "ubt" / "skin.css").read_text()
    assert "Created" in out.getvalue()


@pytest.mark.parametrize("key", ["UBT", "my skin", "-ubt", "k" * 33])
def test_a_key_that_cannot_be_a_skin_is_refused_and_leaves_nothing_behind(skins_dir, key):
    with pytest.raises(CommandError):
        call_command("startskin", key)
    assert list(skins_dir.iterdir()) == []


def test_an_existing_folder_is_never_overwritten(skins_dir):
    (skins_dir / "ubt").mkdir()
    with pytest.raises(CommandError, match="already exists"):
        call_command("startskin", "ubt")
