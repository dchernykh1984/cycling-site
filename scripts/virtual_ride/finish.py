"""A built route and what stands round it, made one map entry and put into its map file:

python -I finish.py route.json around.json meta.json map.js

meta.json: {id, name, desc, event, scenery, origin?, mountains?, ...} -- what a person writes; route.json the
geometry (build_route.py); around.json the surroundings (surroundings.py). The route's tunnels get their real
profile here: 6.5 m under the ground line between ramps 100 m long, the barometer having smoothed the dip away.
"""

import itertools
import json
import math
import sys
from pathlib import Path

route_path, around_path, meta_path, map_path = sys.argv[1:5]
route = json.loads(Path(route_path).read_text(encoding="utf-8"))
around = json.loads(Path(around_path).read_text(encoding="utf-8"))
meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
pts = route["pts"]
KX, KY = 111320 * math.cos(math.radians(pts[0][0])), 111195
cum = [0.0]
for a, b in itertools.pairwise(pts):
    cum.append(cum[-1] + math.hypot((b[1] - a[1]) * KX, (b[0] - a[0]) * KY))
L = cum[-1] + math.hypot((pts[0][1] - pts[-1][1]) * KX, (pts[0][0] - pts[-1][0]) * KY)
RAMP, DEPTH = 100.0, 6.5


def index_at(s):
    s %= L
    return min(range(len(pts)), key=lambda i: abs(cum[i] - s))


tunnels = []
for i0, i1 in around.pop("tunnels", []):
    r0, r1 = index_at(cum[i0] - RAMP), index_at(cum[i1] + RAMP)
    if not (r0 < i0 <= i1 < r1):
        print(
            f"tunnel {i0}-{i1}: its ramps run past the loop's start, left as the barometer has it",
            file=sys.stderr,
        )
        continue
    y0, y1 = pts[r0][2], pts[r1][2]
    for i in range(r0, r1 + 1):
        f = (cum[i] - cum[r0]) / (cum[r1] - cum[r0])
        ground = y0 + (y1 - y0) * f
        if cum[i] < cum[i0]:
            k = (cum[i] - cum[r0]) / (cum[i0] - cum[r0])
        elif cum[i] > cum[i1]:
            k = (cum[r1] - cum[i]) / (cum[r1] - cum[i1])
        else:
            k = 1.0
        shape = k * k * (3 - 2 * k)  # a ramp that eases in and out
        pts[i][2] = round(ground - DEPTH * shape, 1)
    tunnels.append([r0, i0, i1, r1])
    print(
        f"tunnel: points {r0} {i0} {i1} {r1}, ground {y0:.1f}..{y1:.1f} m, its floor 6.5 m under it",
        file=sys.stderr,
    )

entry = {
    k: meta[k] if k in meta else route[k]
    for k in (
        "id",
        "name",
        "loop",
        "width",
        "lanes",
        "oneway",
        "scenery",
        "origin",
        "mountains",
    )
    if k in meta or k in route
}
for k in ("loop", "width", "lanes", "oneway"):
    if k not in meta:
        entry[k] = route[k]
entry["desc"] = meta["desc"]
entry["event"] = meta["event"]
entry["pts"] = pts
for k in ("buildings", "roads", "over", "under", "bridges", "lines", "water", "trees"):
    v = around.get(k)
    if v and (not isinstance(v, dict) or any(v.values())):
        entry[k] = v
if tunnels:
    entry["tunnels"] = tunnels
if not entry.get("oneway"):
    entry.pop("oneway", None)

src = Path(map_path).read_text(encoding="utf-8")


def dump(v):
    return json.dumps(v, ensure_ascii=False, separators=(", ", ": "))


FIRST = ("id", "name", "loop", "width", "lanes", "oneway", "scenery", "origin", "mountains")


def route_text(r):
    """A route as the map files lay one out: its short fields on the first line, every other a line of its own."""
    lines = [", ".join(f'"{k}": {dump(r[k])}' for k in FIRST if k in r)]
    lines += [f'"{k}": {dump(v)}' for k, v in r.items() if k not in FIRST]
    return "{" + ",\n     ".join(lines) + "}"


def put_in_array(src, key, item_text, item_id):
    """The JSON array under `key` with item_text in place of the item of that id, else after the last: the other
    items keep their text as it is."""
    dec = json.JSONDecoder()
    a = src.index(f'"{key}": [') + len(f'"{key}": ')
    arr, end = dec.raw_decode(src, a)
    items, pos = [], a + 1
    for _ in arr:
        while src[pos] in " \n,":
            pos += 1
        obj, nxt = dec.raw_decode(src, pos)
        items.append((obj, src[pos:nxt]))
        pos = nxt
    texts = [t for obj, t in items if obj.get("id") != item_id] + [item_text]
    return src[:a] + "[\n    " + ",\n    ".join(texts) + "\n  ]" + src[end:]


new = put_in_array(src, "routes", route_text(entry), entry["id"])
s0 = new.index("addMap(") + 7
json.loads(new[s0 : new.rindex(")")])  # still JSON
Path(map_path).write_text(new, encoding="utf-8")
print(f"{map_path}: {len(src) // 1024} KB -> {len(new) // 1024} KB", file=sys.stderr)
