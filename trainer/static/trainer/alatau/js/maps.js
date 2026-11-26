'use strict';
/* ---------------- Maps: a city or a region each, in a folder of its own (maps/<id>/map.js) ---------------- */
// A map's file calls addMap with its data, and the page loads that file: alatau.html lists the maps in the
// order the menu shows them. The data is JSON -- keys in double quotes, no trailing commas, no comments inside --
// which the site's tests read too. Names are { ru, kk, en }, points [latitude, longitude, height in metres]; the scene
// is laid out in metres east and south of the map's origin, a point among its routes. A map with mountains
// ({ south: metres }) has a range rising to the south, its foot that far south of the origin or further.
// A route far from the map's others -- a region's lie tens of kilometres apart -- carries its own origin, a point
// among its own points, and its own mountains: the map's are then for its other routes.
// A route's point may carry a fourth value, every point or none: the rider's line, metres right of the road's middle
// -- the source track's way through a corner it took by the apex, the right lane elsewhere. A one-way carriageway is
// "oneway": true, its lanes parted by dashes alone.
// A route may also carry its own buildings ({ h: metres, pts: [[latitude, longitude], ...], c: "#rrggbb" where the
// colour is known }, drawn as OpenStreetMap's are), barriers ({ gap: metres }: a guardrail and a catch fence that far
// beyond each edge, broken at the buildings), trees ({ rows: [lines], woods: [rings], pts: [places] }) in place of
// the scattered ones, and what stands round it (js/surroundings.js) -- each where OpenStreetMap maps it:
//   roads   [{ w: metres, pts, lanes }]   the roads it meets and passes, on the ground, rising onto its own
//   over    [{ w, pts, foot }]            bridges over it, a footbridge's (foot) or a road's: the deck's line
//   under   [{ w, pts }]                  roads that go under it, down a cutting
//   bridges [[i0, i1]]                    stretches of it on a bridge, as indexes of its points: parapets
//   tunnels [[r0, i0, i1, r1]]            a stretch in a tunnel between i0 and i1, its ramps from r0 and to r1
//   lines   [{ k, pts }]                  power lines (k "power" on towers, "minor" on poles) and railways ("rail")
//   water   [{ w, pts } | { area }]       rivers and canals; lakes and ponds as their shore's ring
// A map may carry its relief ({ lat: [north, step, rows], lon: [west, step, columns], h: [metres, row by row from the
// north] }): the land round its routes from SRTM, drawn in place of a range beyond the scenery's own ground,.
// A map without routes yet is shown as coming soon.
// A new map: a folder like maps/almaty/ and its line in alatau.html; a new kind of sight: its object's file in
// objects/ and its line (js/landmarks.js).
const CITIES = [], ROUTES = [], LANDMARKS = [];
function addMap(map) {
  const routes = map.routes || [];
  CITIES.push({ id: map.id, name: L(map.name) + (routes.length ? '' : ', ' + t('city.soon')), ready: routes.length > 0, origin: map.origin, mountains: map.mountains || null, relief: map.relief || null });
  routes.forEach(r => ROUTES.push(Object.assign({}, r, { city: map.id, name: L(r.name), desc: L(r.desc) })));
  (map.landmarks || []).forEach(l => LANDMARKS.push(Object.assign({}, l, { city: map.id, name: L(l.name) })));
}
const mapOf = route => CITIES.find(c => c.id === route.city);
