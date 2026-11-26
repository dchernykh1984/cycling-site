"""What stands round a route made before these tools, put into its map entry where it stands:

python -I surround_existing.py map.js osm.json route_id [keep,...]

- the route's own bridges and tunnels: OSM highway ways tagged so whose every 5 m lies on the route's road (within its
  half width and 3 m) running its way; a "tunnel" under 30 m is the road at grade under a footbridge or a pipe
- its points: such a route is sparse (a point a few hundred metres apart on a straight), so points every 5 m go in
  on a structure and 20 m either side of it, every 10 m along a tunnel's ramps, their heights on the line between
  the two points either side
- what stands round it: surroundings.py, the route's own structures its `ways`
- a tunnel's floor 6.5 m under the ground line between ramps of 100 m, as finish.py lays one
- keep: fields the entry keeps as they are (the Sokol Racetrack's buildings and trees, set by hand)
"""

import itertools
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

map_path, osm_path, rid = sys.argv[1:4]
KEEP = set(sys.argv[4].split(",")) if len(sys.argv) > 4 else set()
RAMP, DEPTH, SHORT = 100.0, 6.5, 30.0
DRIVE = {
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street",
    "service", "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
}  # fmt: skip

src = Path(map_path).read_text(encoding="utf-8")
data = json.loads(src[src.index("addMap(") + 7 : src.rindex(")")])
entry = next(r for r in data["routes"] if r["id"] == rid)
osm = json.loads(Path(osm_path).read_text(encoding="utf-8"))
pts = [list(p) for p in entry["pts"]]
LOOP, W = bool(entry.get("loop")), entry["width"]
KX, KY = 111320 * math.cos(math.radians(pts[0][0])), 111195


def xy(lat, lon):
    return (lon * KX, lat * KY)


def course(points):
    """The route's segments, each (a, b, index of a), and the distance along it at each segment's start."""
    p = [xy(q[0], q[1]) for q in points]
    n = len(p)
    seg = [(p[i], p[(i + 1) % n], i) for i in range(n if LOOP else n - 1)]
    cum = [0.0]
    for a, b, _ in seg:
        cum.append(cum[-1] + math.dist(a, b))
    return seg, cum


def near(p, seg, cum):
    """(distance from the route, its heading there, the distance along it)"""
    best = (1e18, 0.0, 0.0)
    for k, (a, b, _) in enumerate(seg):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length2 = dx * dx + dy * dy or 1
        f = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2))
        d = math.hypot(p[0] - a[0] - dx * f, p[1] - a[1] - dy * f)
        if d < best[0]:
            best = (d, math.atan2(dy, dx), cum[k] + f * math.sqrt(length2))
    return best


def structures(points):
    """(from, to along the route, kind, way id) of each bridge and tunnel the route rides on"""
    seg, cum = course(points)
    found = []
    for e in osm:
        t = e["tags"]
        if e["t"] != "w" or t.get("highway") not in DRIVE:
            continue
        bridge, tunnel = t.get("bridge") not in (None, "no"), t.get("tunnel") not in (None, "no")
        if not (bridge or tunnel):
            continue
        way = [xy(*q) for q in e["ll"]]
        samples = []
        for a, b in itertools.pairwise(way):
            n = max(1, int(math.dist(a, b) // 5))
            heading = math.atan2(b[1] - a[1], b[0] - a[0])
            samples += [((a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n), heading) for k in range(n)]
        on = []
        for p, heading in samples:
            d, along, s = near(p, seg, cum)
            turn = abs((heading - along + math.pi) % (2 * math.pi) - math.pi)
            ok = (
                turn < math.radians(30)
                if t.get("oneway") in ("yes", "1")
                else min(turn, math.pi - turn) < math.radians(30)
            )
            if d < W / 2 + 3 and ok:
                on.append(s)
        length = sum(math.dist(a, b) for a, b in itertools.pairwise(way))
        if samples and len(on) / len(samples) >= 0.8 and not (tunnel and not bridge and length < SHORT):
            found.append((min(on), max(on), "bridge" if bridge else "tunnel", e["id"]))
    return sorted(found)


def densify(points, spans):
    """the points with others put in along the spans (from, to, step), each on the line between its neighbours"""
    seg, cum = course(points)
    out = []
    for k, (_, _, i) in enumerate(seg):
        a, b = points[i], points[(i + 1) % len(points)]
        out.append(a)
        s0, s1 = cum[k], cum[k + 1]
        adds = {
            round(s, 1)
            for f, t, step in spans
            for s in (f + step * j for j in range(int((t - f) // step) + 1))
            if s0 + 1 < s < s1 - 1
        }
        for s in sorted(adds):
            g = (s - s0) / (s1 - s0)
            out.append(
                [
                    round(a[0] + (b[0] - a[0]) * g, 6),
                    round(a[1] + (b[1] - a[1]) * g, 6),
                    round(a[2] + (b[2] - a[2]) * g, 1),
                ]
            )
    if not LOOP:
        out.append(points[-1])
    return out


found = structures(pts)
spans = [(f - 20, t + 20, 5.0) for f, t, _, _ in found]
spans += [(f - RAMP - 10, t + RAMP + 10, 10.0) for f, t, kind, _ in found if kind == "tunnel"]
if spans:
    pts = densify(pts, spans)
print(
    f"{rid}: {[(round(f), round(t), k) for f, t, k, _ in found]}, {len(entry['pts'])} -> {len(pts)} points",
    file=sys.stderr,
)

route = {"pts": pts, "loop": LOOP, "width": W, "lanes": entry.get("lanes", 2), "ways": [w for *_, w in found]}
if entry.get("oneway"):
    route["oneway"] = True
with tempfile.TemporaryDirectory() as tmp:
    route_json, around_json = Path(tmp) / "route.json", Path(tmp) / "around.json"
    route_json.write_text(json.dumps(route), encoding="utf-8")
    tool = Path(__file__).with_name("surroundings.py")
    subprocess.run(  # noqa: S603 -- the tools' own script and the current interpreter, no shell
        [sys.executable, "-I", str(tool), str(route_json), osm_path, str(around_json)], check=True
    )
    around = json.loads(around_json.read_text(encoding="utf-8"))

# a bridge two ways draw (a carriageway and the one beside it) is one stretch
for kind in ("bridges", "tunnels"):
    merged: list[list[int]] = []
    for r0, r1 in sorted(around.get(kind, [])):
        if merged and r0 <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], r1)
        else:
            merged.append([r0, r1])
    around[kind] = merged

# a tunnel's profile, as finish.py lays it
_, cum = course(pts)


def index_at(s):
    return min(range(len(pts)), key=lambda i: abs(cum[i] - s))


tunnels = []
for i0, i1 in around.pop("tunnels", []):
    r0, r1 = index_at(cum[i0] - RAMP), index_at(cum[i1] + RAMP)
    if not (r0 < i0 <= i1 < r1):
        print(f"tunnel {i0}-{i1}: its ramps run past the start, left as it is", file=sys.stderr)
        continue
    y0, y1 = pts[r0][2], pts[r1][2]
    for i in range(r0, r1 + 1):
        ground = y0 + (y1 - y0) * (cum[i] - cum[r0]) / (cum[r1] - cum[r0])
        if cum[i] < cum[i0]:
            k = (cum[i] - cum[r0]) / (cum[i0] - cum[r0])
        elif cum[i] > cum[i1]:
            k = (cum[r1] - cum[i]) / (cum[r1] - cum[i1])
        else:
            k = 1.0
        pts[i][2] = round(ground - DEPTH * k * k * (3 - 2 * k), 1)
    tunnels.append([r0, i0, i1, r1])
    print(f"tunnel: points {r0} {i0} {i1} {r1}, ground {y0:.1f}..{y1:.1f} m", file=sys.stderr)

entry["pts"] = pts
for key in ("buildings", "roads", "over", "under", "bridges", "lines", "water", "trees"):
    v = around.get(key)
    if key not in KEEP and v and (not isinstance(v, dict) or any(v.values())):
        entry[key] = v
if tunnels:
    entry["tunnels"] = tunnels


def dump(v):
    return json.dumps(v, ensure_ascii=False, separators=(", ", ": "))


FIRST = ("id", "name", "loop", "width", "lanes", "oneway", "scenery", "origin", "mountains")
lines = [", ".join(f'"{k}": {dump(entry[k])}' for k in FIRST if k in entry)]
lines += [f'"{k}": {dump(v)}' for k, v in entry.items() if k not in FIRST]
text = "{" + ",\n     ".join(lines) + "}"

# the entry's text in its place, every other text as it is
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
print(f"{map_path}: {len(src) // 1024} KB -> {len(new) // 1024} KB", file=sys.stderr)
