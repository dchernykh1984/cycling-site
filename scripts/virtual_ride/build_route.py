"""Build a virtual-ride route from a ride's laps and OpenStreetMap: python -I build_route.py config.json

config (JSON):
  ride, laps, osm, relief   paths: the decoded ride, its passes of the lap's anchor, the area's OSM features,
                            an SRTM grid
  first, per                laps begin at pass `first`, `per` passes each (2 for a lap through its anchor twice)
  start                     [lat, lon] of the start line, or null: the loop then begins at the lap's first pass
  out                       the JSON written: the route's points and what stands round it
  near                      optional {buildings, roads, lines, water, trees} distances in metres

The road is the OSM ways the median lap ran on (map-matched with Viterbi: distance, direction, one-way, class and
continuity), corners rounded to the road's width, gaps OSM does not cover (a turn across a median) from the laps' own
mean track. Heights: the barometer, each lap's mean taken off, the laps averaged by place along the lap, smoothed over
100 m and set on SRTM's mean height along the route. The rider's line: the laps' mean offset from the road's middle
(+ right), smoothed over 30 m, used where the road turns and the right lane elsewhere.
"""

import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
ride = json.loads(Path(cfg["ride"]).read_text(encoding="utf-8"))
laps_meta = json.loads(Path(cfg["laps"]).read_text(encoding="utf-8"))
osm = json.loads(Path(cfg["osm"]).read_text(encoding="utf-8"))
relief = json.loads(Path(cfg["relief"]).read_text(encoding="utf-8"))
NEAR = {"buildings": 350, "roads": 450, "lines": 2500, "water": 1500, "trees": 1300, **cfg.get("near", {})}
recs = [r for r in ride["records"] if r["lat"] is not None and r["dist"] is not None]
P = laps_meta["passes"]
FIRST, PER = cfg["first"], cfg["per"]

LAT0 = sum(r["lat"] for r in recs) / len(recs)
KX, KY = 111320 * math.cos(math.radians(LAT0)), 111195


def xy(lat, lon):
    return (lon * KX, lat * KY)


def ll(p):
    return (p[1] / KY, p[0] / KX)


def dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def ang(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


# ---------------------------------------------------------------- the laps
laps = [recs[P[k] : P[k + PER] + 1] for k in range(FIRST, len(P) - PER, PER)]
lens = [lp[-1]["dist"] - lp[0]["dist"] for lp in laps]
med = sorted(lens)[len(lens) // 2]
laps = [lp for lp, n in zip(laps, lens, strict=False) if abs(n - med) < 0.02 * med]
base = min(laps, key=lambda lp: abs(lp[-1]["dist"] - lp[0]["dist"] - med))
print(f"{len(laps)} laps of about {med:.0f} m", file=sys.stderr)

# ---------------------------------------------------------------- OSM ways
RIDE_CLASSES = {
    "motorway": 0,
    "trunk": 0,
    "primary": 0,
    "secondary": 0,
    "tertiary": 0,
    "unclassified": 0,
    "residential": 0,
    "living_street": 1,
    "road": 1,
    "raceway": 0,
    "track": 3,
    "service": 4,
    "motorway_link": 3,
    "trunk_link": 3,
    "primary_link": 3,
    "secondary_link": 3,
    "tertiary_link": 3,
}
ways = []
for e in osm:
    if e["t"] == "w" and len(e["ll"]) > 1:
        e["xy"] = [xy(*p) for p in e["ll"]]
        ways.append(e)
roads = [w for w in ways if w["tags"].get("highway") in RIDE_CLASSES]
CELL = 40
grid = defaultdict(list)
for wi, w in enumerate(roads):
    for si, (a, b) in enumerate(zip(w["xy"], w["xy"][1:], strict=False)):
        for gx in range(int(min(a[0], b[0]) // CELL) - 1, int(max(a[0], b[0]) // CELL) + 2):
            for gy in range(int(min(a[1], b[1]) // CELL) - 1, int(max(a[1], b[1]) // CELL) + 2):
                grid[(gx, gy)].append((wi, si))
along_cache: dict[int, list[float]] = {}


def along(wi):
    if wi not in along_cache:
        c = [0.0]
        for a, b in zip(roads[wi]["xy"], roads[wi]["xy"][1:], strict=False):
            c.append(c[-1] + dist(a, b))
        along_cache[wi] = c
    return along_cache[wi]


def oneway(t):
    return (
        t.get("oneway") in ("yes", "1", "true") or t.get("junction") == "roundabout" or t.get("highway") == "motorway"
    )


node_ways = defaultdict(set)  # a shared node: the same coordinates in two ways
for wi, w in enumerate(roads):
    for p in w["ll"]:
        node_ways[tuple(p)].add(wi)

# ---------------------------------------------------------------- map matching of the median lap
SIGMA, FREE = 6.0, 9.0
pts = [xy(r["lat"], r["lon"]) for r in base]
heads = []
for i in range(len(pts)):
    a, b = pts[max(0, i - 2)], pts[min(len(pts) - 1, i + 2)]
    heads.append(math.atan2(b[1] - a[1], b[0] - a[0]))


def candidates(i):
    p, h, out = pts[i], heads[i], {}
    for wi, si in grid.get((int(p[0] // CELL), int(p[1] // CELL)), []):
        w = roads[wi]
        a, b = w["xy"][si], w["xy"][si + 1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        len2 = dx * dx + dy * dy or 1
        f = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / len2))
        q = (a[0] + dx * f, a[1] + dy * f)
        d = dist(p, q)
        if d > 25:
            continue
        turn = abs(ang(math.atan2(dy, dx) - h))
        if oneway(w["tags"]) and turn > math.pi / 2:
            continue
        off = min(turn, math.pi - turn)
        cost = (d / SIGMA) ** 2 / 2 + 6 * off * off + RIDE_CLASSES[w["tags"]["highway"]]
        pos = along(wi)[si] + f * math.sqrt(len2)
        if wi not in out or cost < out[wi][0]:
            out[wi] = (cost, q, pos, si)
    res = [(c, wi, q, pos, si) for wi, (c, q, pos, si) in out.items()]
    res.append((FREE, None, p, 0.0, 0))  # off OSM: the ride's own point
    return res


def junction(wa, wb):
    """The shared nodes of two ways."""
    return [p for p in roads[wa]["ll"] if wb in node_ways[tuple(p)]]


C = [candidates(i) for i in range(len(pts))]
cost = [[c[0] for c in C[0]]]
back: list[list[int | None]] = [[None] * len(C[0])]
for i in range(1, len(pts)):
    step = dist(pts[i - 1], pts[i])
    row, brow = [], []
    for c in C[i]:
        best, bj = math.inf, None
        for j, pc in enumerate(C[i - 1]):
            if pc[1] is None or c[1] is None:
                t = 0 if pc[1] is None and c[1] is None else 2.0
            elif pc[1] == c[1]:
                t = abs(abs(c[3] - pc[3]) - step) / 4
            else:
                js = junction(pc[1], c[1])
                if js:
                    n = min(js, key=lambda q: dist(xy(*q), pc[2]) + dist(xy(*q), c[2]))
                    t = 1 + abs(dist(pc[2], xy(*n)) + dist(xy(*n), c[2]) - step) / 4
                else:
                    t = 12.0
            v = cost[-1][j] + t
            if v < best:
                best, bj = v, j
        row.append(best + c[0])
        brow.append(bj)
    cost.append(row)
    back.append(brow)
k = min(range(len(cost[-1])), key=lambda j: cost[-1][j])
path = []
for i in range(len(pts) - 1, -1, -1):
    path.append(C[i][k])
    bk = back[i][k]
    k = bk if bk is not None else 0
path.reverse()
free = sum(1 for c in path if c[1] is None)
print(f"matched {len(path) - free} of {len(path)} points to OSM ways, {free} off them", file=sys.stderr)

# ---------------------------------------------------------------- the road's line from the matched ways
line: list[Any] = []


def put(p):
    if not line or dist(line[-1], p) > 0.8:
        line.append(p)


used: Counter[int] = Counter()
for i, c in enumerate(path):
    if i and c[1] is not None and path[i - 1][1] == c[1]:
        wi, pa, pb = c[1], path[i - 1][3], c[3]
        A, W = along(wi), roads[wi]["xy"]
        if pb > pa:
            for v in range(len(W)):
                if pa < A[v] < pb:
                    put(W[v])
        else:
            for v in range(len(W) - 1, -1, -1):
                if pb < A[v] < pa:
                    put(W[v])
    elif i and c[1] is not None and path[i - 1][1] is not None:
        js = junction(path[i - 1][1], c[1])
        if js:
            put(xy(*min(js, key=lambda q: dist(xy(*q), path[i - 1][2]) + dist(xy(*q), c[2]))))
    if c[1] is not None:
        used[c[1]] += 1
        put(c[2])
    else:
        put(c[2])
# off OSM the ride's own points: smooth them over five points so a turn is one curve, not GPS noise
smooth = list(line)
offmask = []
for p in line:
    near_free = any(dist(p, c[2]) < 1e-6 for c in path if c[1] is None)
    offmask.append(near_free)
for i in range(len(line)):
    if offmask[i]:
        five = [line[(i + j) % len(line)] for j in range(-2, 3)]
        smooth[i] = (sum(q[0] for q in five) / 5, sum(q[1] for q in five) / 5)
line = smooth

# ---------------------------------------------------------------- width, lanes, one-way
lanes: Counter[int] = Counter()
onew: Counter[bool] = Counter()
for wi, n in used.items():
    t = roads[wi]["tags"]
    if t.get("lanes", "").isdigit():
        lanes[int(t["lanes"])] += n
    onew[oneway(t)] += n
LANES = cfg.get("lanes") or (lanes.most_common(1)[0][0] if lanes else 2)
ONEWAY = cfg.get("oneway", onew[True] > onew[False])
WIDTH = cfg.get("width") or round(LANES * 3.5 + (1 if ONEWAY else 0), 1)
print(f"lanes {LANES}, one way {ONEWAY}, width {WIDTH} m; lanes tagged {lanes.most_common(4)}", file=sys.stderr)

# ---------------------------------------------------------------- corners rounded to a turn the road's width allows


def fillet(poly, radius):
    out = [poly[0]]
    n = len(poly)
    for i in range(1, n - 1):
        a, b, c = out[-1], poly[i], poly[i + 1]
        h1, h2 = math.atan2(b[1] - a[1], b[0] - a[0]), math.atan2(c[1] - b[1], c[0] - b[0])
        turn = ang(h2 - h1)
        if abs(turn) < math.radians(12):
            out.append(b)
            continue
        cut = min(radius * math.tan(abs(turn) / 2), dist(a, b) * 0.45, dist(b, c) * 0.45)
        r = cut / math.tan(abs(turn) / 2)
        p0 = (b[0] - math.cos(h1) * cut, b[1] - math.sin(h1) * cut)
        k = max(2, int(abs(turn) * r / 2.5))
        sgn = 1 if turn > 0 else -1
        cx, cy = p0[0] - math.sin(h1) * r * sgn, p0[1] + math.cos(h1) * r * sgn
        for j in range(k + 1):
            t = h1 + turn * j / k
            out.append((cx + math.sin(t) * r * sgn, cy - math.cos(t) * r * sgn))
    out.append(poly[-1])
    return out


def simplify(poly, tol):
    """Douglas-Peucker: the fewest points within tol metres of the line."""
    if len(poly) < 3:
        return poly
    a, b = poly[0], poly[-1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy) or 1
    far, k = -1.0, 0
    for i in range(1, len(poly) - 1):
        d = abs(dy * (poly[i][0] - a[0]) - dx * (poly[i][1] - a[1])) / length
        if d > far:
            far, k = d, i
    if far <= tol:
        return [a, b]
    return simplify(poly[: k + 1], tol)[:-1] + simplify(poly[k:], tol)


# the loop opened at its point furthest from a corner, simplified, then its corners rounded
def despike(poly):
    """Drop a point the line doubles back at over a few metres: a match past a junction's node and back to it."""
    changed = True
    while changed:
        changed = False
        for i in range(len(poly)):
            a, b, c = poly[i - 1], poly[i], poly[(i + 1) % len(poly)]
            t = abs(ang(math.atan2(c[1] - b[1], c[0] - b[0]) - math.atan2(b[1] - a[1], b[0] - a[0])))
            if t > math.radians(100) and min(dist(a, b), dist(b, c)) < 6:
                del poly[i]
                changed = True
                break
    return poly


line = despike(line)
far = max(range(len(line)), key=lambda i: dist(line[0], line[i]))  # a closed line has no chord: split it in two
line = simplify(line[: far + 1], 0.6)[:-1] + simplify([*line[far:], line[0]], 0.6)[:-1]
line = fillet([*line, line[0]], WIDTH / 2 + 8)[:-1]
dedup = [line[0]]
for p in line[1:]:
    if dist(p, dedup[-1]) >= 0.8:
        dedup.append(p)
line = dedup
# a loop: drop the end that comes back onto the start
while len(line) > 3 and dist(line[-1], line[0]) < 2:
    line.pop()
cum = [0.0]
for a, b in zip(line, line[1:] + line[:1], strict=False):
    cum.append(cum[-1] + dist(a, b))
LEN = cum[-1]
print(f"road {LEN:.0f} m from {len(line)} points (the laps: {med:.0f} m)", file=sys.stderr)


def project(p, s_hint=None, window=120, bearing=None):
    """Where p is along the loop: (distance from the road, s along it, signed offset + right of travel); with a
    bearing (degrees from north) only on a stretch going within 90 degrees of it."""
    best = (1e18, 0.0, 0.0)
    n = len(line)
    idx = range(n)
    if s_hint is not None:
        idx = [i for i in range(n) if abs(ang((cum[i] - s_hint) / LEN * 2 * math.pi)) * LEN / (2 * math.pi) < window]
    for i in idx:
        a, b = line[i], line[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        if bearing is not None and abs(ang(math.atan2(dx, dy) - math.radians(bearing))) > math.pi / 2:
            continue
        len2 = dx * dx + dy * dy or 1
        f = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / len2))
        qx, qy = a[0] + dx * f, a[1] + dy * f
        d = math.hypot(p[0] - qx, p[1] - qy)
        if d < best[0]:
            side = 1 if (dx * (p[1] - a[1]) - dy * (p[0] - a[0])) < 0 else -1
            best = (d, cum[i] + f * math.sqrt(len2), side * d)
    return best


# ---------------------------------------------------------------- the start line: the loop begins 20 m before it
if cfg.get("start"):
    d, s0, _ = project(xy(*cfg["start"]), bearing=cfg.get("start_bearing"))
    s0 = (s0 - 20) % LEN
    i0 = max(i for i in range(len(line)) if cum[i] <= s0)
    line = line[i0:] + line[:i0]
    cum = [0.0]
    for a, b in zip(line, line[1:] + line[:1], strict=False):
        cum.append(cum[-1] + dist(a, b))
    print(f"start line {d:.1f} m off the road; the loop begins 20 m before it", file=sys.stderr)

dense = []
for i, a in enumerate(line):
    b = line[(i + 1) % len(line)]
    k = int(dist(a, b) // 20)
    dense.append(a)
    for j in range(1, k + 1):
        f = j / (k + 1)
        dense.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
line = dense
cum = [0.0]
for a, b in zip(line, line[1:] + line[:1], strict=False):
    cum.append(cum[-1] + dist(a, b))

# ---------------------------------------------------------------- heights and the rider's line, by place along the loop
BIN = 5
nb = int(LEN // BIN) + 1
hs, hn, os_, on = [0.0] * nb, [0] * nb, [0.0] * nb, [0] * nb
for lp in laps:
    mean = sum(r["alt"] for r in lp if r["alt"] is not None) / len(lp)
    hint = None
    for r in lp:
        p = xy(r["lat"], r["lon"])
        d, s, off = project(p, hint, 150) if hint is not None else project(p)
        if hint is not None and d > 30:
            d, s, off = project(p)
        hint = s
        b = min(nb - 1, int(s // BIN))
        if r["alt"] is not None:
            hs[b] += r["alt"] - mean
            hn[b] += 1
        if d < 15:
            os_[b] += off
            on[b] += 1


def fill(vals, counts):
    out = [v / c if c else None for v, c in zip(vals, counts, strict=False)]
    known = [i for i, v in enumerate(out) if v is not None]
    for i in range(len(out)):
        if out[i] is None:
            j = min(known, key=lambda k: min(abs(k - i), len(out) - abs(k - i)))
            out[i] = out[j]
    return out


def smooth_loop(vals, half):
    n = len(vals)
    return [sum(vals[(i + j) % n] for j in range(-half, half + 1)) / (2 * half + 1) for i in range(n)]


rel_h = smooth_loop(fill(hs, hn), 10)
offs = smooth_loop(fill(os_, on), 3)


def at(vals, s):
    x = (s % LEN) / BIN - 0.5
    i = math.floor(x)
    f = x - i
    return vals[i % nb] * (1 - f) + vals[(i + 1) % nb] * f


# SRTM's mean height along the route
la0, dla, nr = relief["lat"]
lo0, dlo, nc = relief["lon"]
G = relief["grid"]


def srtm(lat, lon):
    fi, fj = (lat - la0) / dla, (lon - lo0) / dlo
    i, j = int(fi), int(fj)
    u, v = fi - i, fj - j
    return G[i][j] * (1 - u) * (1 - v) + G[i + 1][j] * u * (1 - v) + G[i][j + 1] * (1 - u) * v + G[i + 1][j + 1] * u * v


shift = sum(srtm(*ll(p)) - at(rel_h, cum[i]) for i, p in enumerate(line)) / len(line)
print(f"heights: the barometer's profile set on SRTM's mean {shift:.0f} m", file=sys.stderr)

# the rider's line: the laps' own where the road turns, the right lane elsewhere
KEEP = max(0.0, min(3.2, WIDTH / 2 - 1.5))
turning = []
for i in range(len(line)):
    s = cum[i]
    j0 = min(range(len(line)), key=lambda j: abs(ang((cum[j] - (s - 25)) / LEN * 2 * math.pi)))
    j1 = min(range(len(line)), key=lambda j: abs(ang((cum[j] - (s + 25)) / LEN * 2 * math.pi)))
    a, b, c = line[j0], line[i], line[j1]
    t = ang(math.atan2(c[1] - b[1], c[0] - b[0]) - math.atan2(b[1] - a[1], b[0] - a[0]))
    # + left turn: its inside is to the left, offsets below the right lane's
    turning.append(math.copysign(min(1.0, max(0.0, (math.degrees(abs(t)) - 15) / 20)), t))
# spread the corners' weight 30 m either way so the rider eases onto the apex line and back
n = len(line)
wgt = []
for i in range(n):
    m = 0.0
    for j in range(n):
        d = abs(ang((cum[j] - cum[i]) / LEN * 2 * math.pi)) * LEN / (2 * math.pi)
        if d < 30 and abs(turning[j]) * (1 - d / 30) > abs(m):
            m = turning[j] * (1 - d / 30)
    wgt.append(m)
lim = WIDTH / 2 - 0.8
# One road ridden twice -- a dual carriageway's two halves, a crossing passed on each loop, a road out and back -- has
# one height. The barometer reads late, by its lag times the slope, high one way and low the other: their mean is the
# road's. Points within the road's width and 30 m of another stretch take the mean of the two, near ones fully.
H = [shift + at(rel_h, cum[i]) for i in range(len(line))]
cell: dict[tuple[int, int], list[int]] = {}
for i, p in enumerate(line):
    cell.setdefault((int(p[0] // 40), int(p[1] // 40)), []).append(i)
for _ in range(3):
    new = list(H)
    for i, p in enumerate(line):
        nearest: tuple[float, int] | None = None
        for gx in (-1, 0, 1):
            for gy in (-1, 0, 1):
                for j in cell.get((int(p[0] // 40) + gx, int(p[1] // 40) + gy), ()):
                    apart = abs(cum[i] - cum[j])
                    if min(apart, LEN - apart) < 80:
                        continue
                    d = dist(p, line[j])
                    if d < WIDTH + 30 and (nearest is None or d < nearest[0]):
                        nearest = (d, j)
        if nearest:
            w = 0.5 * min(1.0, max(0.0, (WIDTH + 30 - nearest[0]) / 15))
            new[i] = H[i] * (1 - w) + H[nearest[1]] * w
    H = new
out_pts = []
for i, p in enumerate(line):
    lat, lon = ll(p)
    h = H[i]
    dev = at(offs, cum[i]) - KEEP
    # only a line toward the turn's inside is an apex; one outside is GPS and the map apart, and keeps right
    lane = KEEP + abs(wgt[i]) * dev if dev * wgt[i] < 0 else KEEP
    out_pts.append([round(lat, 6), round(lon, 6), round(h, 1), round(max(-lim, min(lim, lane)), 1)])
# thin the straights to about 10 m, keep every corner point
thin = [out_pts[0]]
for i in range(1, len(out_pts)):
    prev = thin[-1]
    if abs(wgt[i]) > 0.05 or dist(xy(prev[0], prev[1]), line[i]) >= 19 or i == len(out_pts) - 1:
        thin.append(out_pts[i])
print(
    f"points {len(thin)}; heights {min(p[2] for p in thin):.0f}..{max(p[2] for p in thin):.0f} m; "
    f"line {min(p[3] for p in thin)}..{max(p[3] for p in thin)} m (keep {KEEP:.1f})",
    file=sys.stderr,
)

route = {
    "pts": thin,
    "loop": True,
    "width": WIDTH,
    "lanes": LANES,
    "oneway": ONEWAY,
    "ways": sorted({roads[wi]["id"] for wi in used}),
}
Path(cfg["out"]).write_text(json.dumps(route, ensure_ascii=False), encoding="utf-8")
