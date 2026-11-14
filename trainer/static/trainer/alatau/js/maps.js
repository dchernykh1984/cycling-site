'use strict';
/* ---------------- Maps: a city each, in a folder of its own (maps/<id>/map.js) ---------------- */
// A map's file calls addMap with its data, and the page loads that file: alatau.html lists the maps in the
// order the menu shows them. Names are { ru, kk, en }, points [latitude, longitude, height in metres].
// A map without routes yet is shown as coming soon.
const CITIES = [], ROUTES = [], LANDMARKS = [];
function addMap(map) {
  const routes = map.routes || [];
  CITIES.push({ id: map.id, name: L(map.name) + (routes.length ? '' : ', ' + t('city.soon')), ready: routes.length > 0 });
  routes.forEach(r => ROUTES.push(Object.assign({}, r, { city: map.id, name: L(r.name), desc: L(r.desc) })));
  (map.landmarks || []).forEach(l => LANDMARKS.push(Object.assign({}, l, { name: L(l.name) })));
}
