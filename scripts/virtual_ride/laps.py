import itertools
import json
import math
import sys
from pathlib import Path

d = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
name = sys.argv[2]
r = [x for x in d["records"] if x["lat"] is not None and x["dist"] is not None]
lat0 = r[0]["lat"]
kx = 111320 * math.cos(math.radians(lat0))
ky = 111195
xy = [(x["lon"] * kx, x["lat"] * ky) for x in r]
# moving start: first record after which distance grows 30 m in 10 s
i0 = next(i for i in range(len(r) - 10) if r[i + 10]["dist"] - r[i]["dist"] > 30)
# candidate lap anchor: the point 300 m into the ride, so the lap is measured on the circuit itself
a = next(i for i in range(i0, len(r)) if r[i]["dist"] - r[i0]["dist"] > 300)
ax, ay = xy[a]
passes, away = [a], False
for i in range(a + 1, len(r)):
    dd = math.hypot(xy[i][0] - ax, xy[i][1] - ay)
    if dd > 400:
        away = True
    if away and dd < 25:
        # local minimum of distance near the anchor
        j = min(range(i, min(i + 30, len(r))), key=lambda k: math.hypot(xy[k][0] - ax, xy[k][1] - ay))
        passes.append(j)
        away = False
laps = [(r[b]["dist"] - r[a2]["dist"]) for a2, b in itertools.pairwise(passes)]
print(f"{name}: moving from {r[i0]['t'][11:19]}, anchor {r[a]['lat']:.5f},{r[a]['lon']:.5f}; passes {len(passes)}")
print("  laps (m):", [round(x) for x in laps][:30])
if laps:
    lm = sorted(laps)[len(laps) // 2]
    print(
        f"  median lap {lm:.0f} m; total {r[-1]['dist']:.0f} m; "
        f"laps by distance {(r[-1]['dist'] - r[i0]['dist']) / lm:.2f}"
    )
Path(sys.argv[1].replace(".json", ".laps.json")).write_text(
    json.dumps({"i0": i0, "passes": passes, "laps": laps}), encoding="utf-8"
)
