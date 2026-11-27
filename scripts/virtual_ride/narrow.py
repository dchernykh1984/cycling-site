"""A stretch of a route on a narrower road than its own -- Granfondo 2026's frontage roads and their crossing over
Al-Farabi at its near turn, two lanes where the avenue has three, drawn as wide as the avenue:

python -I narrow.py map.js route_id '[{"from": [lat, lon], "to": [lat, lon], "width": metres, "lanes": n}, ...]'

- each stretch: from the route's point nearest ``from`` to the one nearest ``to`` after it, written as the route's
  "narrow" ([[point, point, width, lanes]]; js/track.js eases the road's width to it over 20 m), the riders' line
  there kept to its right lane (js/track.js keepLane: 1.5 m in from its edge, 3.2 m from its middle at most)
"""

import json
import math
import sys
from pathlib import Path

map_path, rid, spec = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])

src = Path(map_path).read_text(encoding="utf-8")
data = json.loads(src[src.index("addMap(") + 7 : src.rindex(")")])
entry = next(r for r in data["routes"] if r["id"] == rid)
pts = entry["pts"]
KX, KY = 111320 * math.cos(math.radians(pts[0][0])), 111195


def nearest(p, after=0):
    return min(range(after, len(pts)), key=lambda i: math.hypot((pts[i][1] - p[1]) * KX, (pts[i][0] - p[0]) * KY))


stretches = []
for s in spec:
    i0 = nearest(s["from"])
    i1 = nearest(s["to"], i0)
    lane = min(3.2, s["width"] / 2 - 1.5)
    for i in range(i0, i1 + 1):
        if len(pts[i]) > 3 and pts[i][3] > lane:
            pts[i][3] = round(lane, 2)
    stretches.append([i0, i1, s["width"], s["lanes"]])
entry["narrow"] = stretches
print(f"{rid}: narrow {stretches}", file=sys.stderr)


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
