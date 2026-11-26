'use strict';
/* ---------------- Maps: a city or a region each, in a folder of its own (maps/<id>/map.js) ---------------- */
// A map's file calls addMap with its data, and the page loads that file: alatau.html lists the maps in the
// order the menu shows them. The data is JSON -- keys in double quotes, no trailing commas, no comments inside --
// which the site's tests read too. Names are { ru, kk, en }, points [latitude, longitude, height in metres]; the scene
// is laid out in metres east and south of the map's origin, a point among its routes. A map with mountains
// ({ south: metres }) has a range rising to the south, its foot that far south of the origin or further.
// A route far from the map's others -- a region's lie tens of kilometres apart -- carries its own origin, a point
// among its own points, and its own mountains: the map's are then for its other routes.
// A route may also carry its own buildings ({ h: metres, pts: [[latitude, longitude], ...] }, drawn as OpenStreetMap's
// are), barriers ({ gap: metres }: a guardrail and a catch fence that far beyond each edge, broken at the buildings)
// and, in the steppe or on a racetrack, trees ({ rows: [lines], woods: [rings] }) in place of the scattered ones --
// each where OpenStreetMap maps it.
// A map may carry its relief ({ lat: [north, step, rows], lon: [west, step, columns], h: [metres, row by row from the
// north] }): the land round its routes from SRTM, drawn in place of a range beyond the scenery's own ground.
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
