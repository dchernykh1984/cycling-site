---
name: virtual-ride-routes
description: Building a route for the virtual ride as the real place is - the roads it meets running off where they really go, turns made on the real road, widths and lanes, the rider on the right, buildings with their floors and look, the relief and what is seen far off, tunnels and bridges, water, trees, and the sources and checks that keep it honest. Read before adding a route to the trainer's maps or changing one.
---

# Virtual ride routes

The maintainer rides these routes on a smart trainer and knows the real places: a route is finished when
riding it looks like riding there. These are their requirements (2026-11-26) and what was added to them.
The data format is in `trainer/static/trainer/alatau/js/maps.js`; the scene is drawn by `js/world.js`.

## What every route carries

1. **Buildings.** Where each one stands, how many floors it has (about 3 m a floor; a shop's or a
   garage's ground floor higher) and, as far as can be found, its look: walls' colour and material,
   windows, roof. Footprints from OpenStreetMap; floors from its `building:levels` or `height`, else
   from photos; colour from `building:colour` or photos. A route's own buildings are its `buildings`
   field (footprints and a height each, drawn as OpenStreetMap's are).
2. **The relief, and what is seen far off.** The ground along the route and the view from it:
   mountain ranges, hills, valleys, lakes and reservoirs. Heights from data -- SRTM 30 m through
   OpenTopoData, or the barometer of a ride on the route averaged over its laps. A range must not end
   in view where the real one goes on: a range 90 km long ended on the left on the way back to
   Kyrbaltabay, 45 km east of the origin, while the real one runs on to 78.3 E.
3. **Tunnels and bridges** the road goes through or over, and bridges over it (footbridges,
   overpasses): OpenStreetMap's `tunnel`, `bridge` and `layer`, and photos.
4. **The road network round the route.**
   - Every road the route meets runs off in its real direction for a stretch: to the horizon on open
     land, a block or two in town.
   - Where the route turns onto a road, both roads are there.
   - Where it turns back, it turns on the road itself, and the road goes on past the turn as in life.
   - Widths and lanes as the road has them: OpenStreetMap's `lanes`, `width` and `oneway`, a dual
     carriageway as its two ways, else measured on satellite imagery. The markings follow the lanes.
   - The rider keeps to the right side of the road, out and back alike -- but where the source track
     takes a corner by its apex while the road runs otherwise, the road is laid as it really runs and
     the rider follows the track's line through the apex.

## Proposed on top -- keep these too

- **Water.** Rivers, canals, lakes and reservoirs (OSM `natural=water`, `waterway`), flat at their
  level, with a bridge where the route crosses one. On flat land the water further than about 5-10 km
  is below the horizon: do not draw what cannot be seen from a saddle.
- **Trees where they grow.** OpenStreetMap's tree rows, woods, orchards and parks rather than random
  planting (a route's `trees` field), and the trees the place has: poplars and elms in the steppe,
  firs in the gorges.
- **Land cover.** Fields, steppe, grass, sand and paved areas from OSM `landuse`/`natural`, not one
  colour to the horizon.
- **Lines seen from the road.** Railways and their level crossings, power lines, canals, walls and
  fences (OSM `railway`, `power=line`, `barrier`).
- **What marks the road.** Signals at junctions, bus stops, kilometre posts; on a circuit its kerbs,
  painted run-offs, guardrails and catch fences (a route's `barriers` field).
- **Sights the rider would name.** Monuments, stadiums, towers -- a map's `landmarks`, built from
  `objects/<type>.js`.
- **The real start and finish.** Where the event starts (a race's own track, its regulations), not the
  first point of a line.
- **The surface.** The asphalt as the place has it -- a circuit's light grey, a village road's patched
  one -- and gravel or concrete where tagged.

## Sources, and saying which is which

- Prefer, in order: the maintainer's own tracks (GPX, FIT) and photos; OpenStreetMap; SRTM through
  OpenTopoData; public articles and photos for heights and looks; satellite imagery only to check
  where things are.
- Tools that answered: `api.openstreetmap.org/api/0.6/map.json?bbox=...` when Overpass is at
  capacity; `api.opentopodata.org/v1/srtm30m` takes 100 points a request, one request a second, 1000 a
  day; `fitdecode` reads a FIT file (positions are semicircles: times 180 / 2^31).
- Tracks are never pulled from Strava's API: its terms forbid it. A track the maintainer gives is fine.
- A ride's power and speed from a bunch are not the road's physics (drafting): take its line and its
  barometer only.
- Every value that is not from a source is a guess, and the map file's comment says so: the Sokol
  Racetrack's heights of buildings and its barrier distance are the model.

## Building a route from a ride's laps (`scripts/virtual_ride/`)

The Institute of Nuclear Physics and Granfondo 2026 routes were built this way; rerun on the same inputs, the tools
give the same data byte for byte.

1. **The laps.** Decode the FIT with `fitdecode` into records of latitude, longitude, height and distance;
   `laps.py ride.json name` finds the passes of an anchor 300 m into the ride. A lap through its anchor twice (a
   figure-eight, a road out and back) is two passes; a first lap that went elsewhere is left out.
2. **OpenStreetMap.** Geofabrik's country extract and `extract_boxes.py` (pyosmium's `FileProcessor` with a
   `KeyFilter`: a Python handler for every node, catching an exception for every way, took an hour, this takes 90 s).
3. **The road** (`build_route.py config.json`): the median lap matched to OSM's ways (Viterbi over distance,
   direction, one-way, class and continuity), a match run past a junction's node and back dropped, the loop
   simplified in two halves, each corner rounded to the road's width plus 8 m. Heights: the barometer, each lap's
   mean taken off, averaged over the laps by place and set on SRTM's mean; one road ridden twice -- a dual
   carriageway's halves, a crossing passed on each loop -- gets one height, since the barometer reads late, by its
   lag times the slope, high one way and low the other. The rider's line: the laps' mean offset from the road's
   middle, used only where the road turns and only toward the turn's inside -- one outside is GPS and the map apart.
   The start line is given with its bearing: beside a dual carriageway its nearest road may run the other way.
4. **What stands round it** (`surroundings.py route.json osm.json out.json [near]`): buildings within 250 m (tall
   ones to 500 m) with heights from `height`, `building:levels` or the kind, colours where tagged; roads that meet
   the route to 400 m, the others to 150 m, no parking aisles; bridges crossing over it, roads under it, its own
   bridges and tunnels; power lines, railways, water, trees. About 70 KB for 7 km in the country, 290 KB for 15 km
   in a city: the map file is the page's, so keep what a rider sees.
5. **Into the map** (`finish.py route.json around.json meta.json map.js`, meta the names, description and event in
   three languages): a tunnel gets its real profile, 6.5 m under the ground line between ramps of 100 m -- the
   barometer smooths the dip away -- and the route goes into the map's routes, the other entries' text untouched.
6. **Look at it.** The route on satellite imagery (zoom 17 to 19, coloured from start to end, arrows every 150 m),
   then in a browser: its start, every turn, the tunnel, under each footbridge, sideways at each sight, and from above
   round the sights.

Sights for a route: a sight that spreads over the land (a cable car, ski jumps) stands each of its parts on the land
under it and marks them (`userData.stands`); its `reach` keeps it to the routes it stands on drawn land for. A hill a
sight stands on gets a detail grid in the map's relief (SRTM 30 m about 150 m apart, through OpenTopoData).

## Checks before calling a route done

- The data tests: `tests/test_virtual_ride_maps.py` (names in three languages, origins within 50 km,
  keys, shapes of buildings, barriers and trees).
- The scene tests: `tests/e2e/test_virtual_ride.py` -- trees, houses and sights in the ground, nothing
  on the road or its shoulder, road ridden twice drawn once, barriers beyond the edges -- and
  `tests/e2e/test_virtual_ride_surroundings.py`: roads under the route where they cross it, bridges clear of it,
  a tunnel's roof over it, a median's barrier and power lines off it, the rider's line on the road.
- Look at it: screenshots from the saddle at the start, at every turn and junction, on the way back
  and towards the far relief; a top view next to satellite imagery.
- Keep it light for phones: trees and posts instanced, a route's buildings one mesh, far relief on a
  coarse grid.
