"""An out-and-back route made a loop: its far turnaround repeated at its start, so a rider back at the start turns
there as at the far end and rides out again, lap after lap:

python -I turn_at_start.py map.js route_id

The far turnaround is the shortest stretch that leaves a point of the route and comes back to the very same point
(a loop round, between the way out and the way back); its copy is turned from the way it is ridden into to the way
the route comes back into its start, and goes after the route's last point, at the start's height. The route's
other point indexes keep their meaning: nothing is put before them.
"""

import json
import math
import sys
from pathlib import Path

map_path, rid = sys.argv[1:3]
src = Path(map_path).read_text(encoding="utf-8")
data = json.loads(src[src.index("addMap(") + 7 : src.rindex(")")])
entry = next(r for r in data["routes"] if r["id"] == rid)
pts = entry["pts"]
if entry.get("loop") or pts[0][:2] != pts[-1][:2]:
    sys.exit(f"{rid}: not a route that comes back to its start")
KX, KY = 111320 * math.cos(math.radians(pts[0][0])), 111195


def xy(p):
    return (p[1] - pts[0][1]) * KX, (p[0] - pts[0][0]) * KY


# the far turnaround: the shortest stretch from a point back to that same point
pairs = [(a, b) for a in range(1, len(pts) - 1) for b in range(a + 3, min(len(pts) - 1, a + 200))]
k1, k2 = min(((a, b) for a, b in pairs if pts[a][:2] == pts[b][:2]), key=lambda ab: ab[1] - ab[0])


def way(a, b):
    (ax, ay), (bx, by) = xy(pts[a]), xy(pts[b])
    return math.atan2(by - ay, bx - ax)


turn = way(len(pts) - 2, len(pts) - 1) - way(k1 - 1, k1)  # from the way into the far one to the way into the start
c, s = math.cos(turn), math.sin(turn)
jx, jy = xy(pts[k1])
copy = []
for p in pts[k1 + 1 : k2]:
    dx, dy = xy(p)[0] - jx, xy(p)[1] - jy
    x, y = dx * c - dy * s, dx * s + dy * c
    copy.append([round(pts[0][0] + y / KY, 6), round(pts[0][1] + x / KX, 6), pts[-1][2]])
entry["pts"] = pts + copy
entry["loop"] = True
print(f"{rid}: the turnaround of points {k1}-{k2} repeated at the start, {len(copy)} points", file=sys.stderr)


def dump(v):
    return json.dumps(v, ensure_ascii=False, separators=(", ", ": "))


# the entry's text in its place, every other text as it is (as surround_existing.py writes one)
FIRST = ("id", "name", "loop", "width", "lanes", "oneway", "scenery", "origin", "mountains")
lines = [", ".join(f'"{k}": {dump(entry[k])}' for k in FIRST if k in entry)]
lines += [f'"{k}": {dump(v)}' for k, v in entry.items() if k not in FIRST]
text = "{" + ",\n     ".join(lines) + "}"
dec = json.JSONDecoder()
start = src.index('"routes": [') + len('"routes": ')
arr, _end = dec.raw_decode(src, start)
pos, new = start + 1, src
for _ in arr:
    while src[pos] in " \n,":
        pos += 1
    obj, nxt = dec.raw_decode(src, pos)
    if obj.get("id") == rid:
        new = src[:pos] + text + src[nxt:]
        break
    pos = nxt
json.loads(new[new.index("addMap(") + 7 : new.rindex(")")])  # still JSON
Path(map_path).write_text(new, encoding="utf-8")
