"""What stands round a built route, from the area's OSM features: python -I surroundings.py route.json osm.json out.json

Adds to the route (lat/lon rounded to ~0.1 m):
  buildings  [{h, pts, c?}]       footprints within NEAR[buildings] of the road; h from height, levels, else the kind
  roads      [{w, pts, lanes?}]   drivable ways within NEAR[roads], cut where they run along the route itself
  over       [{w, pts, foot?}]    bridges over the route: a footbridge or a road, its deck's line where it crosses
  under      [{w, pts}]           roads that go under the route in a tunnel or a cutting
  bridges    [[i0, i1]]           stretches of the route on a bridge, as indexes of its points
  tunnels    [[i0, i1]]           stretches of the route in a tunnel -- not a gallery through a dam (OSM waterway=dam):
                                  the road runs level through it, the dam a sight standing over it
  lines      [{k, pts}]           power lines (k "power"), minor ones ("minor") and railways ("rail")
  water      [{w, pts}|{area}]    rivers, canals and streams; lakes and ponds
  trees      {rows, woods, pts}   tree rows, woods, orchards and parks, single trees; a wood OSM gives its leaf_type
                                  goes to firs (needleleaved), broad (broadleaved) or mixed instead of woods

The fourth argument, JSON, sets the distances above and "own_rest": 1 -- the route's own ways drawn where it does not
ride them, a dual carriageway's other half beside a stretch ridden one way (the Institute of Nuclear Physics' Alatau
road); without it a way the route rides is left out whole.
"""

import itertools
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

route_path, osm_path, out_path = sys.argv[1:4]
route = json.loads(Path(route_path).read_text(encoding="utf-8"))
osm = json.loads(Path(osm_path).read_text(encoding="utf-8"))
LEAF = {"needleleaved": "firs", "broadleaved": "broad", "mixed": "mixed"}  # a wood by its leaves, else woods
NEAR = {"buildings": 250, "roads": 400, "side": 150, "lines": 2500, "water": 1500, "trees": 500}
if len(sys.argv) > 4:
    NEAR.update(json.loads(sys.argv[4]))
W = route["width"]
LAT0 = route["pts"][0][0]
KX, KY = 111320 * math.cos(math.radians(LAT0)), 111195


def xy(lat, lon):
    return (lon * KX, lat * KY)


def ll(p):
    return [round(p[1] / KY, 5), round(p[0] / KX, 5)]


def dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


P = [xy(p[0], p[1]) for p in route["pts"]]
N = len(P)
SEG = (
    [(P[i], P[(i + 1) % N], i) for i in range(N)] if route.get("loop") else [(P[i], P[i + 1], i) for i in range(N - 1)]
)
CELL = 50
grid = defaultdict(list)
for k, (a, b, _) in enumerate(SEG):
    for gx in range(int(min(a[0], b[0]) // CELL) - 1, int(max(a[0], b[0]) // CELL) + 2):
        for gy in range(int(min(a[1], b[1]) // CELL) - 1, int(max(a[1], b[1]) // CELL) + 2):
            grid[(gx, gy)].append(k)


def seg_near(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    len2 = dx * dx + dy * dy or 1
    f = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / len2))
    return math.hypot(p[0] - a[0] - dx * f, p[1] - a[1] - dy * f), f


def gap(p, heading=None):
    """Distance from the route's middle line; with a heading, only to stretches running within 35 degrees of it."""
    best = 1e18
    cx, cy = int(p[0] // CELL), int(p[1] // CELL)
    ks = set()
    for gx in range(cx - 1, cx + 2):
        for gy in range(cy - 1, cy + 2):
            ks.update(grid.get((gx, gy), ()))
    if not ks:  # far: the coarse way
        return min(dist(p, q) for q in P[::4])
    for k in ks:
        a, b, _ = SEG[k]
        if heading is not None:
            h = math.atan2(b[1] - a[1], b[0] - a[0])
            t = abs((h - heading + math.pi) % (2 * math.pi) - math.pi)
            if min(t, math.pi - t) > math.radians(35):
                continue
        best = min(best, seg_near(p, a, b)[0])
    return best


def crossing(a, b):
    """Where segment a-b crosses the route: (point, route segment index) or None."""
    cx0, cx1 = sorted((a[0], b[0]))
    cy0, cy1 = sorted((a[1], b[1]))
    ks = set()
    for gx in range(int(cx0 // CELL) - 1, int(cx1 // CELL) + 2):
        for gy in range(int(cy0 // CELL) - 1, int(cy1 // CELL) + 2):
            ks.update(grid.get((gx, gy), ()))
    for k in ks:
        c, d, i = SEG[k]
        den = (b[0] - a[0]) * (d[1] - c[1]) - (b[1] - a[1]) * (d[0] - c[0])
        if abs(den) < 1e-9:
            continue
        t = ((c[0] - a[0]) * (d[1] - c[1]) - (c[1] - a[1]) * (d[0] - c[0])) / den
        u = ((c[0] - a[0]) * (b[1] - a[1]) - (c[1] - a[1]) * (b[0] - a[0])) / den
        if 0 <= t <= 1 and 0 <= u <= 1:
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t), i
    return None


def simplify(poly, tol):
    if len(poly) < 3:
        return poly
    a, b = poly[0], poly[-1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    far, k = -1.0, 0
    for i in range(1, len(poly) - 1):
        d = abs(dy * (poly[i][0] - a[0]) - dx * (poly[i][1] - a[1])) / length if length else dist(a, poly[i])
        if d > far:
            far, k = d, i
    if far <= tol:
        return [a, b]
    return simplify(poly[: k + 1], tol)[:-1] + simplify(poly[k:], tol)


def closed(e):
    return len(e["ll"]) > 3 and e["ll"][0] == e["ll"][-1]


def centroid(pts):
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def area(pts):
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1], strict=False))) / 2


out: dict[str, Any] = {
    "buildings": [],
    "roads": [],
    "over": [],
    "under": [],
    "lines": [],
    "water": [],
    "trees": {"rows": [], "woods": [], "pts": []},
}
ways = [e for e in osm if e["t"] == "w"]
for e in ways:
    e["xy"] = [xy(*p) for p in e["ll"]]

# ---------------------------------------------------------------- buildings
KIND_H = {
    "house": 6,
    "detached": 6,
    "semidetached_house": 6,
    "bungalow": 4,
    "cabin": 3.5,
    "farm_auxiliary": 4,
    "garage": 3,
    "garages": 3,
    "shed": 2.6,
    "hut": 3,
    "kiosk": 3,
    "roof": 4,
    "carport": 3,
    "greenhouse": 3,
    "industrial": 8,
    "warehouse": 9,
    "hangar": 11,
    "service": 4,
    "transformer_tower": 6,
    "retail": 6,
    "commercial": 12,
    "office": 18,
    "hotel": 30,
    "apartments": 15,
    "residential": 9,
    "dormitory": 15,
    "school": 10,
    "kindergarten": 7,
    "university": 14,
    "college": 12,
    "hospital": 15,
    "public": 10,
    "civic": 10,
    "government": 12,
    "church": 14,
    "mosque": 12,
    "temple": 10,
    "train_station": 10,
    "sports_hall": 11,
    "stadium": 18,
    "grandstand": 10,
    "parking": 9,
    "yes": 6,
}
KIND_C = {
    "house": "#c9b49a",
    "detached": "#c9b49a",
    "garage": "#a9a69e",
    "garages": "#a9a69e",
    "shed": "#9c8f7a",
    "industrial": "#b4b8bb",
    "warehouse": "#aab3ba",
    "hangar": "#aeb6bd",
    "farm_auxiliary": "#a89c88",
    "apartments": "#ddd3c2",
    "residential": "#d8cdb8",
    "dormitory": "#d8cdb8",
    "retail": "#cfc6b6",
    "commercial": "#c6ccd1",
    "office": "#a8b6c4",
    "university": "#d9cfbd",
    "school": "#dcc9a8",
    "kindergarten": "#e0c9a0",
    "hospital": "#e4e0d6",
    "church": "#ece6da",
    "mosque": "#e8e4dc",
}


def height(t):
    for k in ("height", "building:height"):
        v = t.get(k, "").replace("m", "").replace(",", ".").strip()
        try:
            if v:
                return max(2.5, float(v))
        except ValueError:
            pass
    lv = t.get("building:levels", "").strip()
    if lv.replace(".", "", 1).isdigit():
        n = float(lv)
        return round(
            n * 3.1 + (1.2 if n >= 2 else 0.6) + (1.5 if t.get("roof:shape", "flat") not in ("flat", "") else 0),
            1,
        )
    return KIND_H.get(t.get("building", "yes"), 6)


def colour(t):
    c = t.get("building:colour") or t.get("colour")
    if c and c.startswith("#") and len(c) in (4, 7):
        return c.lower()
    named = {
        "white": "#ecebe6",
        "grey": "#a9aaa7",
        "gray": "#a9aaa7",
        "beige": "#d8c9a8",
        "yellow": "#e3cf8a",
        "brown": "#8f6a4c",
        "red": "#b45a46",
        "orange": "#d99a5a",
        "blue": "#8fa6bd",
        "green": "#93a88a",
        "pink": "#e0b8b0",
        "cream": "#ece2c6",
        "silver": "#c3c6c9",
        "maroon": "#7a3b32",
    }
    if c and c.lower() in named:
        return named[c.lower()]
    return KIND_C.get(t.get("building", "yes"))


for e in ways:
    t = e["tags"]
    if "building" not in t or not closed(e) or t.get("building") in ("no", "construction", "ruins", "roof"):
        continue
    if t.get("layer", "0").lstrip("-").isdigit() and int(t.get("layer", "0")) < 0:
        continue
    ring = e["xy"][:-1]
    c = centroid(ring)
    tall = height(t) >= 30
    if gap(c) > (NEAR["buildings"] * 2 if tall else NEAR["buildings"]) or area(ring) < 8:
        continue
    if min(gap(p) for p in ring) < W / 2 + 2:  # on the road: OSM's or the ride's line a metre off
        continue
    ring = simplify([*ring, ring[0]], 0.5)[:-1]
    if len(ring) < 3:
        continue
    b = {"h": height(t), "pts": [ll(p) for p in ring][:40]}
    col = colour(t)
    if col:
        b["c"] = col
    out["buildings"].append(b)

# ------------------------------------------------------------- roads round the route, bridges over it, roads under it
DRIVE = {
    "motorway",
    "trunk",
    "primary",
    "secondary",
    "tertiary",
    "unclassified",
    "residential",
    "living_street",
    "service",
    "motorway_link",
    "trunk_link",
    "primary_link",
    "secondary_link",
    "tertiary_link",
    "road",
    "track",
    "raceway",
}
FOOT = {"footway", "path", "cycleway", "steps", "pedestrian", "bridleway"}
CLASS_W = {
    "motorway": 11,
    "trunk": 11,
    "primary": 11,
    "secondary": 9,
    "tertiary": 7.5,
    "unclassified": 6,
    "residential": 6,
    "living_street": 5,
    "service": 4.5,
    "track": 3.5,
    "raceway": 10,
    "road": 6,
    "motorway_link": 6,
    "trunk_link": 6,
    "primary_link": 6.5,
    "secondary_link": 6,
    "tertiary_link": 6,
}
own_ids = set(route.get("ways", []))


def width_of(t):
    try:
        return max(2.0, float(t.get("width", "").replace("m", "").strip()))
    except ValueError:
        pass
    if t.get("lanes", "").isdigit():
        return round(int(t["lanes"]) * 3.3 + 0.5, 1)
    return CLASS_W.get(t.get("highway"), 5)


def layer(t):
    v = t.get("layer", "0").strip()
    return int(v) if v.lstrip("-").isdigit() else 0


for e in ways:
    t = e["tags"]
    hw = t.get("highway")
    if hw not in DRIVE and hw not in FOOT:
        continue
    lay, pts = layer(t), e["xy"]
    hit = None
    for a, b in itertools.pairwise(pts):
        hit = hit or crossing(a, b)
    bridge = t.get("bridge") not in (None, "no") or lay > 0
    tunnel = t.get("tunnel") not in (None, "no") or lay < 0 or t.get("cutting") in ("yes",)
    if e["id"] in own_ids and not NEAR.get("own_rest"):
        continue

    def across(hit, pts=pts):
        a, b = pts[0], pts[-1]
        c, d, _ = SEG[hit[1]]
        t = abs(
            (math.atan2(b[1] - a[1], b[0] - a[0]) - math.atan2(d[1] - c[1], d[0] - c[0]) + math.pi) % (2 * math.pi)
            - math.pi
        )
        return min(t, math.pi - t) > math.radians(30)

    if hit and not across(hit):
        hit = None
    if hit and bridge:
        # over the route: the deck from end to end, as OSM draws the bridge
        out["over"].append(
            {
                "w": width_of(t) if hw in DRIVE else max(2.5, width_of(t) if "width" in t else 3),
                "pts": [ll(p) for p in simplify(pts, 0.5)],
                **({"foot": True} if hw in FOOT else {}),
            }
        )
        continue
    if hit and tunnel and hw in DRIVE:
        out["under"].append({"w": width_of(t), "pts": [ll(p) for p in simplify(pts, 0.5)]})
        continue
    if hw in FOOT or bridge or tunnel:
        continue
    meets = min(gap(p) for p in pts) < W / 2 + 40
    if not meets and (hw == "service" or t.get("service") in ("parking_aisle", "driveway")):
        continue
    reach = NEAR["roads"] if meets else NEAR["side"]
    # a road round the route: its parts within reach, cut where it runs on the route's own line
    parts, cur = [], []
    for i, p in enumerate(pts):
        heading = math.atan2(
            pts[min(i + 1, len(pts) - 1)][1] - pts[max(i - 1, 0)][1],
            pts[min(i + 1, len(pts) - 1)][0] - pts[max(i - 1, 0)][0],
        )
        keep = gap(p) < reach and gap(p, heading) > W / 2 + 1
        if keep:
            cur.append(p)
        elif cur:
            if len(cur) > 1 or (i and gap(pts[i - 1]) < reach):
                parts.append(cur + ([p] if gap(p) < reach else []))
            cur = []
    if cur:
        parts.append(cur)
    for part in parts:
        part = simplify(part, 0.7)
        if len(part) < 2 or sum(dist(a, b) for a, b in itertools.pairwise(part)) < 8:
            continue
        r = {"w": width_of(t), "pts": [ll(p) for p in part]}
        if t.get("lanes", "").isdigit():
            r["lanes"] = int(t["lanes"])
        out["roads"].append(r)

# ---------------------------------------------------------------- the route's own bridges and tunnels, as point indexes
DAMS = [e["xy"] for e in ways if e["tags"].get("waterway") == "dam"]
DAM_M = 10.0  # a gallery runs through a dam's body: within its outline, or this near its line


def in_dam(p):
    for ring in DAMS:
        if len(ring) > 3 and dist(ring[0], ring[-1]) < 0.5:  # an outline: inside it
            hit = False
            for (ax, ay), (bx, by) in itertools.pairwise(ring):
                if (ay > p[1]) != (by > p[1]) and p[0] < ax + (bx - ax) * (p[1] - ay) / (by - ay):
                    hit = not hit
            if hit:
                return True
        if min(seg_near(p, a, b)[0] for a, b in itertools.pairwise(ring)) < DAM_M:
            return True
    return False


for e in ways:
    if e["id"] not in own_ids:
        continue
    t = e["tags"]
    kind = (
        "bridges" if t.get("bridge") not in (None, "no") else "tunnels" if t.get("tunnel") not in (None, "no") else None
    )
    if not kind:
        continue
    mid = ((e["xy"][0][0] + e["xy"][-1][0]) / 2, (e["xy"][0][1] + e["xy"][-1][1]) / 2)
    if kind == "tunnels" and in_dam(mid):
        print(f"way {e['id']}: a gallery through a dam, the road level in it", file=sys.stderr)
        continue
    a, b = e["xy"][0], e["xy"][-1]
    h = math.atan2(b[1] - a[1], b[0] - a[0])
    # the route's stretch running the way's way (a dual carriageway has two)
    idx = []
    for i in range(N):
        q = P[(i + 1) % N]
        hh = math.atan2(q[1] - P[i][1], q[0] - P[i][0])
        tt = abs((hh - h + math.pi) % (2 * math.pi) - math.pi)
        if oneway := t.get("oneway") in ("yes", "1"):
            ok = tt < math.radians(40)
        else:
            ok = min(tt, math.pi - tt) < math.radians(40)
        if ok and min(seg_near(P[i], e["xy"][j], e["xy"][j + 1])[0] for j in range(len(e["xy"]) - 1)) < W / 2 + 2:
            idx.append(i)
    if idx:
        runs: list[list[int]] = []
        start = idx[0]
        for x, y in zip(idx, [*idx[1:], None], strict=False):
            if y is None or y != x + 1:
                runs.append([start, x])
                start = y if y is not None else start
        for r0, r1 in runs:
            if r1 >= r0:
                out.setdefault(kind, []).append([r0, min(N - 1, r1 + 1)])


# ---------------------------------------------------------------- power lines, railways, water, trees
def within(pts, reach):
    """The runs of a line within reach of the route, each with the point beyond either end: a power line or a river
    that runs on for tens of kilometres is drawn as far as it is seen."""
    near_ = [gap(p) < reach for p in pts]
    runs, cur = [], []
    for i, p in enumerate(pts):
        if near_[i] or (i + 1 < len(pts) and near_[i + 1]) or (i and near_[i - 1]):
            cur.append(p)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    return [r for r in runs if len(r) > 1]


for e in ways:
    t = e["tags"]
    pts = e["xy"]
    near = min(gap(p) for p in [*pts[:: max(1, len(pts) // 30)], pts[-1]])
    if t.get("power") in ("line", "minor_line") and near < NEAR["lines"]:
        for run in within(pts, NEAR["lines"]):
            out["lines"].append({"k": "power" if t["power"] == "line" else "minor", "pts": [ll(p) for p in run]})
    elif t.get("railway") in ("rail", "light_rail", "narrow_gauge") and near < NEAR["lines"] and not t.get("tunnel"):
        for run in within(simplify(pts, 1), NEAR["lines"]):
            out["lines"].append({"k": "rail", "pts": [ll(p) for p in run]})
    elif t.get("waterway") in ("river", "canal", "stream") and near < NEAR["water"] and not t.get("tunnel"):
        w = {"river": 12, "canal": 6, "stream": 2.5}[t["waterway"]]
        try:
            w = float(t.get("width", w))
        except ValueError:
            pass
        for run in within(simplify(pts, 1), NEAR["water"]):
            out["water"].append({"w": w, "pts": [ll(p) for p in run]})
    elif (
        (t.get("natural") == "water" or t.get("landuse") in ("reservoir", "basin"))
        and closed(e)
        and near < NEAR["water"]
    ):
        shore = [ll(p) for p in simplify(pts, 1.5)[:-1]]
        if len(shore) >= 3:  # a pond a few metres across simplifies to a line: there is nothing to draw
            out["water"].append({"area": shore})
    elif t.get("natural") == "tree_row" and near < min(NEAR["trees"], 300):
        out["trees"]["rows"].append([ll(p) for p in simplify(pts, 1)])
    elif (
        (t.get("natural") == "wood" or t.get("landuse") in ("forest", "orchard") or t.get("leisure") == "park")
        and closed(e)
        and near < NEAR["trees"]
    ):
        outline = [ll(p) for p in simplify(pts, 2)[:-1]]
        if len(outline) >= 3:
            leaf = LEAF.get(t.get("leaf_type", ""), "woods")
            out["trees"].setdefault(leaf, []).append(outline)
for e in osm:
    if e["t"] == "n" and e["tags"].get("natural") == "tree" and gap(xy(*e["ll"])) < NEAR["trees"]:
        out["trees"]["pts"].append(ll(xy(*e["ll"])))
# power towers stand at a line's vertices: OSM's own, the line drawn from tower to tower
summary = {k: (len(v) if isinstance(v, list) else {kk: len(vv) for kk, vv in v.items()}) for k, v in out.items()}
print(json.dumps(summary), file=sys.stderr)
Path(out_path).write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(f"{len(json.dumps(out, separators=(',', ':'))) / 1024:.0f} KB", file=sys.stderr)
