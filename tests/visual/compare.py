"""Compare two sets of screenshots pixel by pixel; write a picture of every difference."""

import json
import pathlib

from PIL import Image, ImageChops, ImageDraw


def _blank(image, rects, offset, scale):
    draw = ImageDraw.Draw(image)
    dx, dy = offset
    for left, top, right, bottom in rects:
        box = [(left - dx) * scale, (top - dy) * scale, (right - dx) * scale, (bottom - dy) * scale]
        draw.rectangle(box, fill=(255, 0, 255))


def compare(before_dir, after_dir, diff_dir):
    """Return a list of human-readable problems; empty when the two sets match."""
    before_meta = json.loads(pathlib.Path(before_dir, "meta.json").read_text())
    after_meta = json.loads(pathlib.Path(after_dir, "meta.json").read_text())
    problems = []
    for name in sorted(set(before_meta) | set(after_meta)):
        if name not in before_meta or name not in after_meta:
            problems.append(f"{name}: taken on one side only")
            continue
        before, after = before_meta[name], after_meta[name]
        if after["overflows"] and not before["overflows"]:
            problems.append(f"{name}: the page now scrolls sideways")
        old = Image.open(pathlib.Path(before_dir, name)).convert("RGB")
        new = Image.open(pathlib.Path(after_dir, name)).convert("RGB")
        if old.size != new.size:
            problems.append(f"{name}: size {old.size} -> {new.size}")
            continue
        # Masked on both sides with the union of both sides' areas, so a control that changed size
        # still hides completely.
        rects = before["masked"] + after["masked"]
        _blank(old, rects, before["offset"], before.get("scale", 1))
        _blank(new, rects, after["offset"], after.get("scale", 1))
        box = ImageChops.difference(old, new).getbbox()
        if box:
            problems.append(f"{name}: differs in {box}")
            target = pathlib.Path(diff_dir, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            side_by_side = Image.new("RGB", (old.width * 2, old.height))
            side_by_side.paste(old, (0, 0))
            side_by_side.paste(new, (old.width, 0))
            ImageDraw.Draw(side_by_side).rectangle(box, outline=(255, 0, 0), width=3)
            side_by_side.save(target)
    return problems
