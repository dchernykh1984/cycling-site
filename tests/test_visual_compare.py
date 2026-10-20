"""The before/after comparison (tests/visual/compare.py) finds what changed and only that."""

import json

from PIL import Image

from tests.visual.compare import compare


def _side(root, *, pixel=None, masked=(), overflows=False, scale=1):
    image = Image.new("RGB", (20, 20), "white")
    if pixel:
        image.putpixel(pixel, (0, 0, 0))
    root.mkdir()
    image.save(root / "shot.png")
    meta = {"shot.png": {"masked": [list(r) for r in masked], "offset": [0, 0], "overflows": overflows, "scale": scale}}
    (root / "meta.json").write_text(json.dumps(meta))
    return root


def test_identical_sets_match(tmp_path):
    assert compare(_side(tmp_path / "a"), _side(tmp_path / "b"), tmp_path / "diff") == []


def test_a_changed_pixel_is_reported_with_a_picture(tmp_path):
    problems = compare(_side(tmp_path / "a"), _side(tmp_path / "b", pixel=(5, 5)), tmp_path / "diff")
    assert problems == ["shot.png: differs in (5, 5, 6, 6)"]
    assert (tmp_path / "diff" / "shot.png").exists()


def test_a_change_under_either_sides_mask_is_ignored(tmp_path):
    before = _side(tmp_path / "a", masked=[(0, 0, 3, 3)])
    after = _side(tmp_path / "b", pixel=(10, 10), masked=[(8, 8, 12, 12)])
    assert compare(before, after, tmp_path / "diff") == []


def test_a_page_that_starts_scrolling_sideways_is_reported(tmp_path):
    problems = compare(_side(tmp_path / "a"), _side(tmp_path / "b", overflows=True), tmp_path / "diff")
    assert problems == ["shot.png: the page now scrolls sideways"]


def test_a_mask_in_css_pixels_covers_a_phone_screenshot_of_denser_pixels(tmp_path):
    before = _side(tmp_path / "a", masked=[(4, 4, 6, 6)], scale=2)
    after = _side(tmp_path / "b", pixel=(10, 10), masked=[(4, 4, 6, 6)], scale=2)
    assert compare(before, after, tmp_path / "diff") == []
