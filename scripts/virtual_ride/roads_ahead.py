"""The road a route turns off going on ahead, drawn as the route's own: on a dual carriageway each half on past where
the route turns back across the median or leaves it for a side road -- Granfondo 2026's Al-Farabi, which went on as
pieces of grey road, so that its turns read as loops:

python -I roads_ahead.py map.js osm.json route_id '[{"from": [lat, lon], "toward": [lat, lon], "highway": kind}, ...]'

- each road: from the OpenStreetMap way nearest ``from`` that runs toward ``toward`` (either way along it: a one-way
  carriageway coming toward the turn is drawn back from it), of the OpenStreetMap class ``highway`` where given -- a
  side road leaving the avenue from the same point, as the frontage road Granfondo leaves it for at its near turn,
  is not it --, AHEAD_M on along it and the ways that go on from its
  end with its name and class, the straightest where there are several
- written as the route's roads marked "onward" and "ahead", of the route's width and lanes (js/surroundings.js draws
  them as its own road); the ones a run before wrote are replaced

osm.json: extract_boxes.py's ways, [{"t": "w", "id", "tags", "ll": [[lat, lon], ...]}].
"""

import json
import math
import sys
from pathlib import Path

map_path, osm_path, rid, spec = sys.argv[1], sys.argv[2], sys.argv[3], json.loads(sys.argv[4])
AHEAD_M = 600.0  # a block or two in a city, as far as the road shows ahead
SAME_NODE_M = 0.5

src = Path(map_path).read_text(encoding="utf-8")
data = json.loads(src[src.index("addMap(") + 7 : src.rindex(")")])
entry = next((r for r in data["routes"] if r["id"] == rid), None)
if entry is None:
    raise SystemExit(f"{map_path} has no route {rid!r}")
origin = entry["pts"][0]
KX, KY = 111320 * math.cos(math.radians(origin[0])), 111195


def xy(p):
    return (p[1] - origin[1]) * KX, (p[0] - origin[0]) * KY


def ll(x, y):
    return [round(origin[0] + y / KY, 6), round(origin[1] + x / KX, 6)]


ways = [
    (f["tags"].get("name"), f["tags"]["highway"], [xy(p) for p in f["ll"]])
    for f in json.loads(Path(osm_path).read_text(encoding="utf-8"))
    if f["t"] == "w" and f["tags"].get("highway") in ("motorway", "trunk", "primary", "secondary", "tertiary")
]


def nearest_way(start, toward, highway=None):
    """The way nearest ``start`` that runs toward ``toward``: (its index, its segment's, the fraction along that, and
    whether toward is the way's own direction)."""
    bx, by = xy(start)
    tx, ty = xy(toward)
    ux, uy = tx - bx, ty - by
    best = None
    for k, (_, kind, line) in enumerate(ways):
        if highway and kind != highway:
            continue
        for i in range(len(line) - 1):
            (sx, sy), (ex, ey) = line[i], line[i + 1]
            dx, dy = ex - sx, ey - sy
            length = math.hypot(dx, dy) or 1
            if abs(dx * ux + dy * uy) / length < 0.7 * math.hypot(ux, uy):  # across the way it should run along
                continue
            g = max(0.0, min(1.0, ((bx - sx) * dx + (by - sy) * dy) / length**2))
            d = math.hypot(bx - sx - dx * g, by - sy - dy * g)
            if best is None or d < best[0]:
                best = (d, k, i, g, dx * ux + dy * uy > 0)
    if best is None:
        raise SystemExit(f"no way near {start} runs toward {toward}")
    return best[1:]


def next_way(road, name, kind, line):
    """The way that goes on from the road's end with this one's name and class, the straightest: (its points from
    there, the way), or None."""
    (ax, ay), (cx, cy) = road[-2], road[-1]
    options = []
    for n2, k2, l2 in ways:
        if (n2, k2) != (name, kind) or l2 is line:
            continue
        for seq in (l2, l2[::-1]):
            if math.dist(seq[0], (cx, cy)) < SAME_NODE_M and len(seq) > 1:
                turn = (cx - ax) * (seq[1][0] - cx) + (cy - ay) * (seq[1][1] - cy)
                options.append((-turn / (math.dist(seq[0], seq[1]) or 1), seq, l2))
    return min(options, key=lambda o: o[0])[1:] if options else None


def ahead(start, toward, highway=None):
    """The road from the way nearest ``start`` toward ``toward``, AHEAD_M along it and on into the ways after it."""
    k, i, g, forward = nearest_way(start, toward, highway)
    name, kind, line = ways[k]
    (sx, sy), (ex, ey) = line[i], line[i + 1]
    road = [(sx + (ex - sx) * g, sy + (ey - sy) * g)]
    rest, left = (line[i + 1 :] if forward else line[i::-1]), AHEAD_M
    while left > 0:
        for px, py in rest:
            qx, qy = road[-1]
            step = math.hypot(px - qx, py - qy)
            if step >= left:
                road.append((qx + (px - qx) * left / step, qy + (py - qy) * left / step))
                left = 0
                break
            road.append((px, py))
            left -= step
        nxt = next_way(road, name, kind, line) if left > 0 else None
        if nxt is None:
            break
        seq, line = nxt
        rest = seq[1:]
    pts = [ll(x, y) for x, y in road]
    return {"w": entry["width"], "pts": pts, "lanes": entry["lanes"], "onward": True, "ahead": True}


roads = [r for r in entry.get("roads", []) if not r.get("ahead")]
entry["roads"] = [*roads, *(ahead(s["from"], s["toward"], s.get("highway")) for s in spec)]
print(f"{rid}: {len(spec)} roads ahead, {len(entry['roads'])} roads", file=sys.stderr)


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
