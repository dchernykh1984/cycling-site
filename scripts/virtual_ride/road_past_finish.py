"""The road a route from one place to another rides going on past its finish, as OpenStreetMap has it -- drawn as the
route's own road, not cut off at the arch:

python -I road_past_finish.py map.js osm.json route_id way_id

- the road: the OpenStreetMap way ``way_id``, from its end at the route's finish, ONWARD_M along it, as a road of the
  way's width (its pieces' own among the route's roads, else the route's) and lanes, marked "onward"; it begins
  ONWARD_LEAD_M before the finish on the route's own line, under its road there (js/surroundings.js)
- the roads round the route that were pieces of that way, all their points within SAME_ROAD_M of it, are dropped

osm.json: extract_boxes.py's ways, [{"t": "w", "id", "tags", "ll": [[lat, lon], ...]}].
"""

import itertools
import json
import math
import sys
from pathlib import Path

map_path, osm_path, rid, way_id = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
ONWARD_M = 1500.0  # to where the valley turns the road out of sight
ONWARD_LEAD_M = 6.0  # as turn_on_road.py: under the route's own road where it begins
SAME_ROAD_M = 3.0

src = Path(map_path).read_text(encoding="utf-8")
data = json.loads(src[src.index("addMap(") + 7 : src.rindex(")")])
entry = next(r for r in data["routes"] if r["id"] == rid)
end = entry["pts"][-1]
KX, KY = 111320 * math.cos(math.radians(end[0])), 111195


def xy(p):
    return (p[1] - end[1]) * KX, (p[0] - end[0]) * KY


def ll(x, y):
    return [round(end[0] + y / KY, 6), round(end[1] + x / KX, 6)]


def gap(p, line):
    """How far a point is from a polyline."""
    best = math.inf
    for (ax, ay), (bx, by) in itertools.pairwise(line):
        dx, dy = bx - ax, by - ay
        f = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / ((dx * dx + dy * dy) or 1)))
        best = min(best, math.hypot(p[0] - ax - dx * f, p[1] - ay - dy * f))
    return best


way = next(f for f in json.loads(Path(osm_path).read_text(encoding="utf-8")) if f["t"] == "w" and f["id"] == way_id)
line = [xy(p) for p in way["ll"]]
if math.hypot(*line[-1]) < math.hypot(*line[0]):  # from its end at the finish
    line.reverse()
# where it begins: ONWARD_LEAD_M back along the route's last stretch, on its line
(px, py), (qx, qy) = xy(entry["pts"][-2]), xy(entry["pts"][-1])
back = math.hypot(qx - px, qy - py)
lead = min(ONWARD_LEAD_M, back)
road, left = [(qx + (px - qx) * lead / back, qy + (py - qy) * lead / back), (qx, qy)], ONWARD_M
for x, y in line:
    lx, ly = road[-1]
    step = math.hypot(x - lx, y - ly)
    if step >= left:
        road.append((lx + (x - lx) * left / step, ly + (y - ly) * left / step))
        break
    if step > 0.5:
        road.append((x, y))
        left -= step
pieces = [
    r for r in entry.get("roads", []) if not r.get("onward") and all(gap(xy(p), road) < SAME_ROAD_M for p in r["pts"])
]
width = max((r["w"] for r in pieces), default=entry["width"])
lanes = int(way["tags"].get("lanes", entry["lanes"]))
entry["roads"] = [r for r in entry.get("roads", []) if r not in pieces and not r.get("onward")]
entry["roads"].append({"w": width, "pts": [ll(x, y) for x, y in road], "lanes": lanes, "onward": True})
print(f"{rid}: way {way_id} on past the finish, {width} m, {len(pieces)} of its pieces dropped", file=sys.stderr)


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
