"""Cut the features round each route out of a country's OSM extract: python -I extract_boxes.py file.osm.pbf outdir"""

import json
import sys
import time
from pathlib import Path

import osmium

pbf, out = sys.argv[1], sys.argv[2]
BOXES = {  # name: (south, west, north, east)
    "almaty": (43.13, 76.84, 43.31, 77.08),
    "institute": (43.322, 77.115, 43.362, 77.175),
    "kyrbaltabay": (43.585, 77.365, 43.705, 77.505),
    "sokol": (43.565, 76.545, 43.600, 76.592),
}
KEYS = (
    "highway",
    "building",
    "building:part",
    "aerialway",
    "attraction",
    "man_made",
    "tourism",
    "historic",
    "waterway",
    "natural",
    "landuse",
    "leisure",
    "power",
    "railway",
    "barrier",
    "bridge",
    "tunnel",
    "amenity",
)


def boxes_of(lat, lon):
    return [n for n, (s, w, no, e) in BOXES.items() if s <= lat <= no and w <= lon <= e]


res: dict[str, list[dict]] = {n: [] for n in BOXES}
t0 = time.time()
fp = osmium.FileProcessor(pbf).with_locations().with_filter(osmium.filter.KeyFilter(*KEYS))
for o in fp:
    if o.is_node():
        hit = boxes_of(o.location.lat, o.location.lon)
        if hit:
            item = {
                "t": "n",
                "id": o.id,
                "tags": dict(o.tags),
                "ll": [round(o.location.lat, 6), round(o.location.lon, 6)],
            }
            for b in hit:
                res[b].append(item)
    elif o.is_way():
        ll = [[round(nd.lat, 6), round(nd.lon, 6)] for nd in o.nodes if nd.location.valid()]
        if not ll:
            continue
        hit = set()
        for la, lo in [*ll[:: max(1, len(ll) // 20)], ll[-1]]:
            hit.update(boxes_of(la, lo))
        if hit:
            item = {"t": "w", "id": o.id, "tags": dict(o.tags), "ll": ll}
            for b in hit:
                res[b].append(item)
for name, items in res.items():
    Path(out, f"{name}.json").write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    print(name, len(items), "features", file=sys.stderr)
print(f"{time.time() - t0:.0f} s", file=sys.stderr)
