"""The streets a route rides, by name, put into its map entry for the page to show under its mini-map:

python -I streets.py map.js osm.json route_id [--whole]

- every 5 m along the route, the nearest highway with a name that runs its way, within half its road and 10 m of
  its middle (a dual carriageway's two halves are two such ways)
- a stretch of one name starts at the route's point where it begins; a stretch under 60 m goes with the one before
  it (a crossing's few metres); a stretch no named way runs along is null, and the page shows nothing there
- names in ru, kk and en: OSM's name:ru, name:kk and name:en (name, the local one, where a language has none), the
  commonest spelling along the stretch; what OSM does not give, NAMES below
- --whole: a route no named street runs along -- a racetrack, a road between two villages -- called by its own name

osm.json: extract_boxes.py's ways, [{"t": "w", "id", "tags", "ll": [[lat, lon], ...]}].
"""

import itertools
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

map_path, osm_path, rid = sys.argv[1:4]
WHOLE = "--whole" in sys.argv[4:]
STEP, SHORT, CELL, PARALLEL = 5.0, 60.0, 50.0, 0.82
# the names OSM leaves out, by the Russian one (escaped: the repository's Python is ASCII)
NAMES = {
    "\u0410\u043b\u0430\u0442\u0430\u0443\u0441\u043a\u0430\u044f \u0442\u0440\u0430\u0441\u0441\u0430": {
        "kk": "\u0410\u043b\u0430\u0442\u0430\u0443 \u0442\u0430\u0441 \u0436\u043e\u043b\u044b",
        "en": "Alatau Highway",
    },
    "\u0443\u043b\u0438\u0446\u0430 \u041b\u044c\u0432\u0430 \u0413\u0443\u043c\u0438\u043b\u0451\u0432\u0430": {
        "kk": "\u041b\u0435\u0432 \u0413\u0443\u043c\u0438\u043b\u0435\u0432 \u043a\u04e9\u0448\u0435\u0441\u0456",
        "en": "Lev Gumilyov Street",
    },
}

src = Path(map_path).read_text(encoding="utf-8")
data = json.loads(src[src.index("addMap(") + 7 : src.rindex(")")])
entry = next(r for r in data["routes"] if r["id"] == rid)
pts = entry["pts"]
KX, KY = 111320 * math.cos(math.radians(pts[0][0])), 111195


def xy(lat, lon):
    return (lon - pts[0][1]) * KX, (lat - pts[0][0]) * KY


def names_of(tags):
    """A way's name in each language, or None for a way without one."""
    ru = tags.get("name:ru") or tags.get("name")
    if not ru:
        return None
    own = NAMES.get(ru, {})
    en = tags.get("name:en") or own.get("en") or tags.get("int_name")
    if en:  # OSM writes "Abay avenue" and "Dostyk Avenue": the kind of street capitalised, as English names go
        en = " ".join(w.capitalize() if w in ("avenue", "street") else w for w in en.split(" "))
    return (ru, tags.get("name:kk") or own.get("kk") or tags.get("name"), en or ru)


def ways_by_cell():
    """The named highways' segments, by the CELL-metre square they pass, and each way's names."""
    grid, named = defaultdict(list), {}
    for f in json.loads(Path(osm_path).read_text(encoding="utf-8")):
        n = names_of(f["tags"]) if f["t"] == "w" and "highway" in f["tags"] else None
        if n is None:
            continue
        named[f["id"]] = n
        for (ax, ay), (bx, by) in itertools.pairwise([xy(a, b) for a, b in f["ll"]]):
            for cx in range(int(min(ax, bx) // CELL) - 1, int(max(ax, bx) // CELL) + 2):
                for cy in range(int(min(ay, by) // CELL) - 1, int(max(ay, by) // CELL) + 2):
                    grid[cx, cy].append((f["id"], ax, ay, bx, by))
    return grid, named


def way_at(grid, x, y, ux, uy):
    """The nearest way running along (ux, uy) within half the road and 10 m of (x, y), or None."""
    best, way = entry["width"] / 2 + 10, None
    for wid, sx, sy, ex, ey in grid.get((int(x // CELL), int(y // CELL)), []):
        dx, dy = ex - sx, ey - sy
        length = math.hypot(dx, dy) or 1
        if abs(dx * ux + dy * uy) / length < PARALLEL:
            continue
        f = max(0.0, min(1.0, ((x - sx) * dx + (y - sy) * dy) / length**2))
        d = math.hypot(x - sx - dx * f, y - sy - dy * f)
        if d < best:
            best, way = d, wid
    return way


def runs_along(grid, named):
    """[first point, Russian name or None, metres, spellings] for each run of one name, every STEP metres matched."""
    route = [xy(p[0], p[1]) for p in pts] + ([xy(pts[0][0], pts[0][1])] if entry.get("loop") else [])
    runs = []
    for k, ((ax, ay), (bx, by)) in enumerate(itertools.pairwise(route)):
        span = math.hypot(bx - ax, by - ay)
        if span < 1e-6:
            continue
        n, ux, uy = max(1, int(span // STEP)), (bx - ax) / span, (by - ay) / span
        for j in range(n):
            name = named.get(way_at(grid, ax + (bx - ax) * j / n, ay + (by - ay) * j / n, ux, uy))
            key = name[0] if name else None
            if not runs or runs[-1][1] != key:
                runs.append([k, key, 0.0, Counter()])
            runs[-1][2] += span / n
            if name:
                runs[-1][3][name] += 1
    return runs


def stretches():
    """[point index, names or None] where each stretch begins; one under SHORT goes with the one before it."""
    kept = []
    for run in runs_along(*ways_by_cell()):
        if kept and (run[2] < SHORT or run[1] == kept[-1][1]):
            kept[-1][2] += run[2]
            kept[-1][3] += run[3]
        else:
            kept.append(run)
    out = []
    for k, key, _metres, spellings in kept:
        # each language's commonest spelling along the stretch
        top = [Counter(s[i] for s in spellings.elements()).most_common(1)[0][0] for i in range(3)] if key else None
        out.append([k, dict(zip(("ru", "kk", "en"), top, strict=True)) if top else None])
    return out


entry["streets"] = [[0, entry["name"]]] if WHOLE else stretches()
for k, n in entry["streets"]:
    print(k, n and n["ru"], file=sys.stderr)


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
