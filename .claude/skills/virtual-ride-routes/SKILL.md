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
   A ride that kept to one carriageway of a dual one both ways, against its one-way tag (the Institute of Nuclear
   Physics' Alatau road, ridden on the left), takes `"against_oneway": true` in the config: matched by traffic's way,
   the course crossed itself.
4. **What stands round it** (`surroundings.py route.json osm.json out.json [near]`): buildings within 250 m (tall
   ones to 500 m) with heights from `height`, `building:levels` or the kind, colours where tagged; roads that meet
   the route to 400 m, the others to 150 m, no parking aisles; bridges crossing over it, roads under it, its own
   bridges and tunnels; power lines, railways and rivers as far as they are seen (2.5 km, 1.5 km), lakes, trees; a
   pond or a wood too small to draw left out. `near` widens a reach where a rider sees further: the Institute of
   Nuclear Physics in the steppe took `'{"buildings": 400, "trees": 1300, "side": 400}'`; `"own_rest": 1` there draws
   the route's own ways where it does not ride them, such as a dual carriageway's other half. About 60 KB for 7 km in
   the country, 280 KB for 15 km in a city: the map file is the page's, so keep what a rider sees.
5. **Into the map** (`finish.py route.json around.json meta.json map.js`, meta the names, description and event in
   three languages): a tunnel gets its real profile, 6.5 m under the ground line between ramps of 100 m -- the
   barometer smooths the dip away -- and the route goes into the map's routes, the other entries' text untouched.
6. **Look at it.** The route on satellite imagery (zoom 17 to 19, coloured from start to end, arrows every 150 m),
   then in a browser: its start, every turn, the tunnel, under each footbridge, sideways at each sight, and from above
   round the sights.

A route made before these tools (Almaty's four, Kyrbaltabay -- Tuganbay, the Sokol Racetrack) got what stands round it
with `surround_existing.py map.js osm.json id [keep,...]`: its own bridges and tunnels found from OSM, points put in
along them so a stretch begins and ends where they do, `surroundings.py`, a tunnel's profile as `finish.py` lays it,
and the entry written where it stands. Sokol keeps its buildings and trees (`buildings,trees`), set by hand. Rerun
from the maps before it on the same extracts, it gives the same files byte for byte.

Two more passes over a map entry, each writing it where it stands:

- `streets.py map.js osm.json id [--whole]`: the streets the route rides, named under the mini-map in three
  languages from OSM's names (the ones OSM lacks in its NAMES); `--whole` names a route no named street runs along
  by its own name (the Sokol Racetrack, Kyrbaltabay -- Tuganbay).
- `turn_on_road.py map.js osm.json id`: an out-and-back route turned round on its road at its far end and at its
  start -- a loop -- from edge to edge, the road going on past each turn as OpenStreetMap has it (`"onward"` roads,
  drawn as the route's own) (Kyrbaltabay -- Tuganbay); laps are a loop's, a route from one place to another ends at
  its finish, and a loop turned at its start finishes a race on its way back past its line.
- `road_past_finish.py map.js osm.json id way_id`: the road a route from one place to another rides, going on
  past its finish along that OpenStreetMap way as the route's own road, its pieces among the roads round the
  route dropped (Medeu's serpentine on to Shymbulak).

A route's picture for an event's link card is its view in the virtual world, `maps/<map>/views/<id>.jpg`, 1200 by
630: rendered from its scene (headless Chromium draws it with SwiftShader), a rider in front of what the route is
known for; the site puts the logo, the day, the time and the title over it (`calendar_app/ride_picture.py`).

Sights for a route: a sight that spreads over the land (a cable car, ski jumps) stands each of its parts on the land
under it and marks them (`userData.stands`), a dam lies on the land it crosses; one that lies flat on the land (a
rink) gives its pad (`addObject`'s third argument) and the ground under it is laid at its level; a building
OpenStreetMap outlines is the `building` object, its name lit on its roof; its `reach` keeps it to the routes it
stands on drawn land for. A hill a
sight stands on gets a detail grid in the map's relief (SRTM 30 m about 150 m apart, through OpenTopoData), and the
summit itself one 30 m fine: between points 150 m apart Kok-Tobe's wheel stood in a dip 24 m under its top.

## Mistakes made on earlier routes -- look for each on a new one

Each was found by the maintainer riding a route; the engine or a tool now avoids it, and a test pins it.

- **Turning back.** A loop round twice the road's width was drawn as a ring where the road goes straight on
  (Kyrbaltabay): riders turn on the road itself, from edge to edge, and the road goes on past the turn as OSM has it
  (`turn_on_road.py`, `"onward"` roads). A loop turned at its start finishes a race on its way back past its line.
- **Laps.** A route from one place to another stops at its finish; only a loop is ridden lap after lap.
- **The land under a sight.** A coarse relief grid set a sight in a dip (the wheel above) or buried it (Medeu's
  rink, 22 m): give a summit a fine grid, a flat sight its pad, and compare the sight's base with SRTM's height there.
- **A sight no rider sees.** A ring thinner than a pixel from the route (the wheel's rim from 1.4 km), a tower behind
  buildings, a business centre no route passed: check each sight from the route at the game's field of view (98
  degrees, not only zoomed in) -- the line of sight over the land and past the buildings -- and draw what is thin
  from afar as lines (wireframe) or thicker the further it stands.
- **Land and roads that do not meet.** Ground over the road (984 points on Medeu), roads round the route sunk in
  folds of the land (6 m), OpenStreetMap's buildings hanging over it (9 m), a street beside a tunnel's ramp over its
  cutting (3 m): the engine handles each now (`sinkUnderRoad`, `onLand`, `footOf`, streets narrowed to the ramp's
  wall); the scene tests find a new case.
- **Jerks.** Heights in steps of 10 points of grade, corners as straight lines between points, a rider swinging round
  a corner in four jerks, a turn of a lane's radius entered at once: heights averaged, positions on a cubic,
  curvature easing in -- the smoothness tests (`test_a_rider_turns_through_every_corner_smoothly`) pin them.
- **A place passed twice.** A loop that passes its start again put that turn's points -- and their rider's line -- at
  its end: a point lies where the route first passes it.
- **Testing a part.** A run of a few tests missed a failing API call and tests whose stubs the page outgrew: after a
  change to the engine or a map, run the four files whole -- `tests/test_virtual_ride_maps.py`,
  `tests/e2e/test_virtual_ride.py`, `tests/e2e/test_virtual_race.py`, `tests/e2e/test_virtual_ride_surroundings.py`
  (`-n 6`; a test that fails only under that load passes on its own: rerun it alone before chasing it).

## Checks before calling a route done

- The data tests: `tests/test_virtual_ride_maps.py` (names in three languages, origins within 50 km,
  keys, shapes of buildings, barriers and trees).
- The scene tests: `tests/e2e/test_virtual_ride.py` -- trees, houses and sights in the ground, nothing
  on the road or its shoulder, road ridden twice drawn once, barriers beyond the edges -- and
  `tests/e2e/test_virtual_ride_surroundings.py`: roads under the route where they cross it, bridges clear of it and the roads onto them climbing onto their decks,
  a tunnel's roof over it and no land left in it or its cutting, a median's barrier and power lines off it, the rider's line on the road.
- Look at it: screenshots from the saddle at the start, at every turn and junction, on the way back
  and towards the far relief; a top view next to satellite imagery.
- Keep it light for phones: trees and posts instanced, a route's buildings one mesh, far relief on a
  coarse grid.
