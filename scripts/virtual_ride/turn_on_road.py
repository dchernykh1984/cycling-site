"""An out-and-back route turned round on the road itself, at its far end and at its start, as riders turn round a
cone -- a loop ridden lap after lap -- and the road going on past each turn as OpenStreetMap has it:

python -I turn_on_road.py map.js osm.json route_id

- the turns: the route's loop round at its far end (the shortest stretch from a point back to that same point) -- or,
  a route out to a point and straight back the same road, that point (a way out alone, build_route.py's out_and_back:
  its last point), its way back then the way there reversed -- and
  the one turn_at_start.py put after its last point, or none there, become turns on the road where each reached: the
  way there keeps the road's middle to SHIFT_M before the turn, then moves to where its rider rides as the rider's
  line (each point's fourth value) comes to the middle -- the rider drifting from their lane to the road's edge --;
  round the turn from edge to edge, its curvature easing in and out over RAMP_M; and back the same way on the other
  side -- the rider's line is the lane everywhere else
- the road on past each turn: the OpenStreetMap way the route rides there, ONWARD_M from ONWARD_LEAD_M before where
  the turn begins, as a road of the route's width and lanes marked "onward": drawn as the route's own road is, which
  gives way to it ONWARD_LEAD_M on (js/surroundings.js)
- heights: a turn's at the height of the point it starts from

osm.json: extract_boxes.py's ways, [{"t": "w", "id", "tags", "ll": [[lat, lon], ...]}].
"""

import json
import math
import sys
from pathlib import Path

map_path, osm_path, rid = sys.argv[1:4]
SHIFT_M = 15.0  # the way there moving from the road's middle to where the rider rides, before the turn
STEP_M = 2.5  # the points' spacing there
RAMP_M = 2.0  # the turn's curvature eases in and out over this, so the rider never swings round at once
POINT_M = 1.0  # the points' spacing round the turn itself
ONWARD_M = 1500.0  # the road drawn on past a turn: to the horizon on the steppe
ONWARD_LEAD_M = 6.0  # it begins so far before the turn, under the route's own road there (js/surroundings.js)
SAME_POINT_M = 0.5
REACH_M = 2.0  # with no loop round to say how far its riders went: the turn begins so far past its last point

src = Path(map_path).read_text(encoding="utf-8")
data = json.loads(src[src.index("addMap(") + 7 : src.rindex(")")])
entry = next(r for r in data["routes"] if r["id"] == rid)
pts = [p[:3] for p in entry["pts"]]
origin = pts[0]
KX, KY = 111320 * math.cos(math.radians(origin[0])), 111195
LANE = min(3.2, entry["width"] / 2 - 1.5)  # js/track.js keepLane: the right lane, 1.5 m in from the edge
EDGE = entry["width"] / 2 - 0.6  # js/track.js laneOf: as near the edge as a rider rides


def xy(p):
    return (p[1] - origin[1]) * KX, (p[0] - origin[0]) * KY


def ll(x, y):
    return round(origin[0] + y / KY, 6), round(origin[1] + x / KX, 6)


def same(a, b):
    return math.dist(xy(a), xy(b)) < SAME_POINT_M


# the way back reaches the start again at the last point equal to the first; what follows is the turn put there
homes = [i for i in range(1, len(pts)) if same(pts[i], pts[0])]
back_home = max(homes) if homes else len(pts) - 1  # a way out alone (build_route.py's out_and_back) comes back to none
pts = pts[: back_home + 1]
pairs = [(a, b) for a in range(1, len(pts) - 1) for b in range(a + 3, min(len(pts) - 1, a + 200))]


def way_to(a, b):
    (ax, ay), (bx, by) = xy(a), xy(b)
    length = math.hypot(bx - ax, by - ay)
    return (bx - ax) / length, (by - ay) / length


def reach(at, ux, uy, loop):
    """How far beyond ``at``, along (ux, uy), a loop round reached: where its riders turned."""
    ax, ay = xy(at)
    return max((xy(p)[0] - ax) * ux + (xy(p)[1] - ay) * uy for p in loop)


def round_the_turn():
    """The rider's way round a turn, from the road's right edge heading on to its left edge heading back: its curvature
    rising over RAMP_M, held, falling over RAMP_M, held as long as edge to edge asks -- [(along, aside)] every POINT_M,
    aside to the right, from (0, EDGE)."""
    ds = 0.005

    def trace(hold):
        peak, total, way, along, aside, out = math.pi / (RAMP_M + hold), 2 * RAMP_M + hold, 0.0, 0.0, EDGE, []
        for k in range(round(total / ds) + 1):
            s = k * ds
            if k % round(POINT_M / ds) == 0:
                out.append((along, aside))
            bend = peak * min(1.0, s / RAMP_M, (total - s) / RAMP_M)
            way += bend * ds
            along += math.cos(way) * ds
            aside -= math.sin(way) * ds
        if math.dist(out[-1], (along, aside)) > POINT_M / 2:  # its end, unless a point stands there already
            out.append((along, aside))
        return out

    low, high = 0.0, 50.0
    for _ in range(60):  # the hold that takes it from edge to edge
        hold = (low + high) / 2
        low, high = (hold, high) if trace(hold)[-1][1] > -EDGE else (low, hold)
    return trace((low + high) / 2)


ROUND = round_the_turn()
TURN_M = SHIFT_M + max(a for a, _ in ROUND)  # from where the way there leaves the road's middle to the turn's far point


loops = [(a, b) for a, b in pairs if same(pts[a], pts[b])] if homes else []  # a way out alone turns at its end


def cut_before(i, metres):
    """The way there up to ``metres`` short of point ``i`` along it, ending on a point put there."""
    left, k = metres, i
    while k > 0:
        step = math.dist(xy(pts[k - 1]), xy(pts[k]))
        if step >= left:
            (ax, ay), (bx, by), f = xy(pts[k - 1]), xy(pts[k]), (step - left) / step
            lat, lon = ll(ax + (bx - ax) * f, ay + (by - ay) * f)
            return [*pts[:k], [lat, lon, round(pts[k - 1][2] + (pts[k][2] - pts[k - 1][2]) * f)]]
        left -= step
        k -= 1
    raise SystemExit("the way there is shorter than a turn")


if loops:
    k1, k2 = min(loops, key=lambda ab: ab[1] - ab[0])
else:  # out to its farthest point and back -- a way out alone to its end --: the way back is the way there reversed
    top = max(range(len(pts)), key=lambda i: math.dist(xy(pts[i]), xy(pts[0]))) if homes else len(pts) - 1
    there = cut_before(top, TURN_M + REACH_M)
    pts = [*there, *there[::-1][1:]]
    k1 = k2 = len(there) - 1


def turn(at, ux, uy, far):
    """The points of a turn on the road from ``at``, on the road's middle and running (ux, uy), to its far point
    ``far`` metres on and back to ``at``: [lat, lon, height, the rider's line]."""
    ax, ay = xy(at)
    rx, ry = uy, -ux  # the right of the way there
    begin = far - TURN_M  # where the way there leaves the middle
    into = begin + SHIFT_M  # where the turn itself begins, at the road's edge
    out = []

    def put(along, aside, line):
        lat, lon = ll(ax + ux * along + rx * aside, ay + uy * along + ry * aside)
        out.append([lat, lon, at[2], round(line, 2)])

    if begin > SAME_POINT_M:
        put(begin, 0, LANE)
    shift = round(SHIFT_M / STEP_M)
    for k in range(1, shift):  # to the edge, the rider's line coming to the middle: the rider drifts out of their lane
        f = k / shift
        put(begin + SHIFT_M * f, EDGE * f, LANE * (1 - f))
    for along, aside in ROUND:  # round the turn, across the road
        put(into + along, aside, 0)
    for k in range(1, shift + 1):  # and back from the other edge to the middle, where the turn began
        f = k / shift
        put(into - SHIFT_M * f, -EDGE * (1 - f), LANE * f)
    return out


def onward(at, ux, uy, far):
    """The road on past a turn: from ONWARD_LEAD_M before where the turn begins, along the OpenStreetMap way the route
    rides there, ONWARD_M the way the turn faces."""
    ax, ay = xy(at)
    begin = far - TURN_M - ONWARD_LEAD_M
    bx, by = ax + ux * begin, ay + uy * begin
    best = None
    for f in json.loads(Path(osm_path).read_text(encoding="utf-8")):
        if f["t"] != "w" or "highway" not in f["tags"]:
            continue
        line = [xy(p) for p in f["ll"]]
        for i in range(len(line) - 1):
            (sx, sy), (ex, ey) = line[i], line[i + 1]
            dx, dy = ex - sx, ey - sy
            length = math.hypot(dx, dy) or 1
            g = max(0.0, min(1.0, ((bx - sx) * dx + (by - sy) * dy) / length**2))
            d = math.hypot(bx - sx - dx * g, by - sy - dy * g)
            if best is None or d < best[0]:
                best = (d, line, i, g, (dx * ux + dy * uy) / length > 0)
    _, line, i, g, forward = best
    (sx, sy), (ex, ey) = line[i], line[i + 1]
    road = [(bx, by)]
    ahead = line[i + 1 :] if forward else line[i::-1]
    left = ONWARD_M
    for px, py in ahead:
        qx, qy = road[-1]
        step = math.hypot(px - qx, py - qy)
        if step >= left:
            road.append((qx + (px - qx) * left / step, qy + (py - qy) * left / step))
            break
        road.append((px, py))
        left -= step
    return {"w": entry["width"], "pts": [list(ll(x, y)) for x, y in road], "lanes": entry["lanes"], "onward": True}


fux, fuy = way_to(pts[k1 - 1], pts[k1])
far_at = reach(pts[k1], fux, fuy, pts[k1 : k2 + 1]) if k2 > k1 else TURN_M + REACH_M
back_home = len(pts) - 1
sux, suy = way_to(pts[back_home - 1], pts[back_home])
start_loop = [p[:3] for p in entry["pts"][back_home:]] if loops else []
start_at = reach(pts[back_home], sux, suy, start_loop) if len(start_loop) > 2 else TURN_M + REACH_M
with_line = [[*p, LANE] for p in pts]
entry["pts"] = (
    with_line[: k1 + 1]
    + turn(pts[k1], fux, fuy, far_at)
    + with_line[k2 : back_home + 1]
    + turn(pts[back_home], sux, suy, start_at)
)
entry["loop"] = True
roads = [r for r in entry.get("roads", []) if not r.get("onward")]
entry["roads"] = [*roads, onward(pts[k1], fux, fuy, far_at), onward(pts[back_home], sux, suy, start_at)]
print(
    f"{rid}: turns {far_at:.1f} m past point {k1} and {start_at:.1f} m past the start, {len(entry['pts'])} points",
    file=sys.stderr,
)


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
