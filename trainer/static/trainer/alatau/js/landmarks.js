'use strict';
/* ---------------- Ориентиры маршрута и арки старта и финиша ---------------- */
// The objects the maps' sights are built from, a file each in objects/: addObject('<type>', build) there, and
// build(G, lm, T, kit) adds one sight's meshes to its group G, which stands at the sight's place (lm: the
// sight's data, T: the route's track). The kit, sizes in metres: lam(colour) is a material; box(w, h, d, colour,
// x, y, z) and cyl(r1, r2, h, colour, x, y, z, segments) stand on y and return their mesh; onion(r, colour, x, y,
// z, spire) puts an onion dome on y, under a golden spire that tall when given. A colour is 0xRRGGBB or a material.
// land(x, z) is the height of the land as drawn at a place on the route's metres, for a sight that spreads over it.
// The ground slopes under a sight: what box and cyl stand at or below its base (y <= 0) reaches kit.sink further
// down, so the sight goes into the ground at its lowest, its top where it was; a shape of its own does the same.
const OBJECTS = {}, PADS = {}, SHAPES = {};
// pad(lm, T), for a sight that lies flat on the ground: { ring: [[x, z], ...] on the route's metres, y, margin } --
// the ground under the ring and margin metres round it is laid at y, under the sight (js/world.js); shape(lm, T), for
// a sight that is the land itself (a dam the route climbs over): a function of (x, z) giving the land's height there,
// or null where it leaves the land be -- the land rises to it, never sinks
function addObject(type, build, pad, shape) { OBJECTS[type] = build; if (pad) PADS[type] = pad; if (shape) SHAPES[type] = shape; }
// the lowest ground under a box's floor plan, on a grid of points across it
function lowestUnder(ground, box) {
  let m = Infinity;
  for (let i = 0; i <= 8; i++) for (let j = 0; j <= 8; j++) m = Math.min(m, ground(box.min.x + (box.max.x - box.min.x) * i / 8, box.min.z + (box.max.z - box.min.z) * j / 8));
  return m;
}
function addLandmark(grp, lm, T, ground, land) {
  const lam = c => new THREE.MeshLambertMaterial({ color: c });
  const M = c => typeof c === 'number' ? lam(c) : c;
  const build = sink => {
    const G = new THREE.Group();
    G.position.set(lm.x, lm.ele != null ? lm.ele : terrainH(T, lm.x, lm.z) + .4, lm.z); // a sight with a height of its own stands at it
    if (lm.rot != null) G.rotation.y = lm.rot;
    const down = y => y <= 0 ? sink : 0;
    const box = (w, h, d, c, x = 0, y = 0, z = 0) => { const k = down(y), m = new THREE.Mesh(new THREE.BoxGeometry(w, h + k, d), M(c)); m.position.set(x, y - k + (h + k) / 2, z); G.add(m); return m; };
    const cyl = (r1, r2, h, c, x = 0, y = 0, z = 0, seg = 16) => { const k = down(y), m = new THREE.Mesh(new THREE.CylinderGeometry(r1, r2, h + k, seg), M(c)); m.position.set(x, y - k + (h + k) / 2, z); G.add(m); return m; };
    const onion = (r, c, x, y, z, spire) => {
      const pts = [[.62, 0], [1, .35], [1.06, .7], [.88, 1.1], [.5, 1.5], [.16, 1.85], [.04, 2.1], [0, 2.15]].map(p => new THREE.Vector2(p[0] * r, p[1] * r));
      const m = new THREE.Mesh(new THREE.LatheGeometry(pts, 16), M(c)); m.position.set(x, y, z); G.add(m);
      if (spire) { cyl(.18, .25, spire, 0xe2b23c, x, y + r * 2.1, z, 6); box(.25, .25, spire * .35, 0xe2b23c, x, y + r * 2.1 + spire * .7, z); }
    };
    if (OBJECTS[lm.type]) OBJECTS[lm.type](G, lm, T, { lam, box, cyl, onion, sink, land: land || ((x, z) => terrainH(T, x, z)) });
    return G;
  };
  let G = build(0);
  if (ground && !G.userData.spread) { // a sight that spreads over the land stands each of its parts on it itself // built once to find its floor plan, then again as deep as the ground under it asks -- and again
    // under the new one where going deeper widens it (a dam's foot keeps to its faces' slopes down a gorge)
    let sink = 0;
    for (let k = 0; k < 4; k++) {
      const box = new THREE.Box3().setFromObject(G), need = box.min.y - lowestUnder(ground, box) + ROOT_M;
      if (need <= 1e-3) break;
      sink += need; G = build(sink);
    }
  }
  grp.add(G);
}
function addArch(grp, T, s, text, W) {
  const o = sampleAt(T, s, {}), g = new THREE.Group(), red = new THREE.MeshLambertMaterial({ color: 0xC3323B });
  [-1, 1].forEach(k => { const p = new THREE.Mesh(new THREE.BoxGeometry(.8, 6.5, .8), red); p.position.set(k * (W / 2 + 1), 3.25, 0); g.add(p); });
  const tex = canvasTex(1024, 128, (c, w, h) => { c.fillStyle = '#C3323B'; c.fillRect(0, 0, w, h); c.fillStyle = '#fff'; c.font = '700 76px Unbounded, sans-serif'; c.textAlign = 'center'; c.textBaseline = 'middle'; c.fillText(text, w / 2, h / 2 + 4); });
  const ban = new THREE.Mesh(new THREE.BoxGeometry(W + 3, 1.6, .5), [red, red, red, red, new THREE.MeshBasicMaterial({ map: tex }), new THREE.MeshBasicMaterial({ map: tex })]);
  ban.position.y = 6.2; g.add(ban);
  g.position.set(o.x, o.y, o.z); g.rotation.y = Math.atan2(o.tx, o.tz); grp.add(g);
}
