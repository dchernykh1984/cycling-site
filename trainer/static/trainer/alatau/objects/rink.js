'use strict';
/* A skating rink on the floor of a valley: its ice as OpenStreetMap outlines it (lm.ice, [[latitude, longitude], ...],
   a speed skater's oval and the field inside it), the oval's lanes drawn on it, the stands rising round it in rows
   of seats to an outer wall, and four floodlight masts over its corners. */
const RINK_DEPTH = 20, rinkLevel = (lm, T) => nearest(T, lm.x, lm.z).y - 1; // the ice lies on the valley's floor
addObject('rink', (G, lm, T, { cyl, box, sink }) => {
  G.position.y = rinkLevel(lm, T);
  let ring = lm.ice.map(p => { const q = proj(p[0], p[1], T.origin); return [q.x - lm.x, q.z - lm.z]; });
  if (ring.length > 2 && ring[0][0] === ring[ring.length - 1][0] && ring[0][1] === ring[ring.length - 1][1]) ring.pop();
  let area = 0; ring.forEach((p, i) => { const q = ring[(i + 1) % ring.length]; area += p[0] * q[1] - q[0] * p[1]; });
  if (area < 0) ring = ring.reverse(); // one way round, so "out" is the same side all along
  const n = ring.length, cx = ring.reduce((s, p) => s + p[0], 0) / n, cz = ring.reduce((s, p) => s + p[1], 0) / n;
  // each point's way out of the ice: the mean of its two edges' outward normals
  const out = ring.map((p, i) => {
    const a = ring[(i + n - 1) % n], b = ring[(i + 1) % n], ex = b[0] - a[0], ez = b[1] - a[1], l = Math.hypot(ex, ez) || 1;
    return [ez / l, -ex / l];
  });
  if ((ring[0][0] - cx) * out[0][0] + (ring[0][1] - cz) * out[0][1] < 0) out.forEach(o => { o[0] = -o[0]; o[1] = -o[1]; });
  const at = (i, d) => [ring[i][0] + out[i][0] * d, ring[i][1] + out[i][1] * d];
  const mesh = (pos, idx, colors, mat) => {
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    if (colors) g.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
    g.setIndex(idx); g.computeVertexNormals(); const m = new THREE.Mesh(g, mat); G.add(m); return m;
  };
  // the ice and the oval's lanes: a red and a blue line four and eight metres in from its edge
  const flat = (pts, y) => { const tris = THREE.ShapeUtils.triangulateShape(pts.map(p => new THREE.Vector2(p[0], p[1])), []), pos = []; pts.forEach(p => pos.push(p[0], y, p[1])); return { pos, idx: tris.flat() }; };
  const ice = flat(ring, .35); mesh(ice.pos, ice.idx, null, new THREE.MeshLambertMaterial({ color: 0xe9f4fb, side: THREE.DoubleSide }));
  [[-4, 0xc8372f], [-8, 0x2a63b0]].forEach(([d, c]) => {
    const pts = []; for (let i = 0; i <= n; i++) { const p = at(i % n, d); pts.push(new THREE.Vector3(p[0], .4, p[1])); }
    G.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: c })));
  });
  // the stands: rows rising from the ice's barrier to the outer wall, blue and red seats in turn
  const ROWS = 8, DEPTH = RINK_DEPTH, RISE = 12, pos = [], col = [], idx = [], c = new THREE.Color(), seat = [0x2a63b0, 0xc8372f];
  for (let k = 0; k < ROWS; k++) { // a row of its own colour: its two edges' points apart from the next row's
    c.setHex(seat[k % 2]);
    for (const e of [k, k + 1]) for (let i = 0; i < n; i++) { const p = at(i, 2 + DEPTH * e / ROWS); pos.push(p[0], 1.2 + RISE * e / ROWS, p[1]); col.push(c.r, c.g, c.b); }
    const o = 2 * k * n;
    for (let i = 0; i < n; i++) { const a = o + i, b = o + (i + 1) % n; idx.push(a, b, b + n, a, b + n, a + n); }
  }
  mesh(pos, idx, col, new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide }));
  // the outer wall, from under the ground to the top row; the barrier round the ice
  const wall = [], wi = [], top = 1.2 + RISE, foot = -3 - sink;
  for (let i = 0; i < n; i++) { const p = at(i, 2 + DEPTH); wall.push(p[0], top, p[1], p[0], foot, p[1]); }
  for (let i = 0; i < n; i++) { const a = 2 * i, b = 2 * ((i + 1) % n); wi.push(a, b, a + 1, b, b + 1, a + 1); }
  mesh(wall, wi, null, new THREE.MeshLambertMaterial({ color: 0xb8b4aa, side: THREE.DoubleSide }));
  const rail = [], ri = [];
  for (let i = 0; i < n; i++) { const p = at(i, 1); rail.push(p[0], 1.4, p[1], p[0], .3, p[1]); }
  for (let i = 0; i < n; i++) { const a = 2 * i, b = 2 * ((i + 1) % n); ri.push(a, b, a + 1, b, b + 1, a + 1); }
  mesh(rail, ri, null, new THREE.MeshLambertMaterial({ color: 0xf2f2ee, side: THREE.DoubleSide }));
  // floodlights over the four corners, their lamps turned to the ice
  [.125, .375, .625, .875].forEach(f => {
    const i = Math.floor(f * n) % n, p = at(i, DEPTH + 8);
    cyl(.5, .9, 44, 0x8d9296, p[0], foot + 3, p[1], 8);
    const lamp = box(8, 4, 1.2, 0xf4f1e6, p[0], 44, p[1]);
    lamp.rotation.y = Math.atan2(cx - p[0], cz - p[1]); lamp.rotation.x = -.35;
  });
}, (lm, T) => ({ ring: lm.ice.map(p => { const q = proj(p[0], p[1], T.origin); return [q.x, q.z]; }), y: rinkLevel(lm, T) - .3, margin: RINK_DEPTH + 25 }));
