'use strict';
/* A viewpoint by the road: its car park of earth as OpenStreetMap outlines it (lm.parking, [[latitude, longitude],
   ...]) laid on the land, a path down from it to a gazebo (lm.gazebo, [latitude, longitude]) -- six posts under a
   pointed roof, a bench round its inside. */
const GAZEBO_R = 2.2, GAZEBO_POSTS = 6, VIEW_PATH_W = 1.2;
addObject('viewpoint', (G, lm, T, { land }) => {
  G.userData.spread = true; G.position.set(lm.x, 0, lm.z);
  const xz = p => { const q = proj(p[0], p[1], T.origin); return { x: q.x - lm.x, z: q.z - lm.z }; };
  const earth = new THREE.MeshLambertMaterial({ color: 0x9a8b70, side: THREE.DoubleSide });
  const at = (x, z, lift) => land(lm.x + x, lm.z + z) + lift;
  // the car park: a sheet over the land, a hand's breadth above it, on a grid fine enough to follow it
  const ring = lm.parking.map(xz), xs = ring.map(p => p.x), zs = ring.map(p => p.z), inside = (x, z) => insideRing(ring.map(p => [p.x, p.z]), x, z);
  const P = [], I = [], step = 1.5, nx = Math.ceil((Math.max(...xs) - Math.min(...xs)) / step), nz = Math.ceil((Math.max(...zs) - Math.min(...zs)) / step);
  const id = new Map();
  for (let i = 0; i <= nx; i++) for (let j = 0; j <= nz; j++) {
    const x = Math.min(...xs) + i * step, z = Math.min(...zs) + j * step;
    id.set(i + ',' + j, P.length / 3); P.push(x, at(x, z, .08), z);
  }
  for (let i = 0; i < nx; i++) for (let j = 0; j < nz; j++) {
    const x = Math.min(...xs) + (i + .5) * step, z = Math.min(...zs) + (j + .5) * step;
    if (!inside(x, z)) continue;
    const a = id.get(i + ',' + j), b = id.get(i + 1 + ',' + j), c = id.get(i + ',' + (j + 1)), d = id.get(i + 1 + ',' + (j + 1));
    I.push(a, c, b, b, c, d);
  }
  // the path from the car park's middle down to the gazebo
  const mid = { x: xs.reduce((s, v) => s + v, 0) / xs.length, z: zs.reduce((s, v) => s + v, 0) / zs.length }, g = xz(lm.gazebo);
  const len = Math.hypot(g.x - mid.x, g.z - mid.z), ux = (g.x - mid.x) / len, uz = (g.z - mid.z) / len, base = P.length / 3;
  const n = Math.ceil(len / 2);
  for (let k = 0; k <= n; k++) {
    const f = k / n * (len - GAZEBO_R), x = mid.x + ux * f, z = mid.z + uz * f;
    [-1, 1].forEach(s => { const px = x - uz * VIEW_PATH_W / 2 * s, pz = z + ux * VIEW_PATH_W / 2 * s; P.push(px, at(px, pz, .06), pz); });
    if (k) { const q = base + k * 2; I.push(q - 2, q - 1, q, q - 1, q + 1, q); }
  }
  const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.Float32BufferAttribute(P, 3)); geo.setIndex(I); geo.computeVertexNormals();
  G.add(new THREE.Mesh(geo, earth));
  // the gazebo on its floor, level at the lowest of the ground under it
  const wood = new THREE.MeshLambertMaterial({ color: 0x7a5a3a }), roof = new THREE.MeshLambertMaterial({ color: 0x6b3b2a });
  let floor = Infinity; for (let k = 0; k < 8; k++) { const a = k / 8 * Math.PI * 2; floor = Math.min(floor, at(g.x + Math.cos(a) * GAZEBO_R, g.z + Math.sin(a) * GAZEBO_R, 0)); }
  const deck = new THREE.Mesh(new THREE.CylinderGeometry(GAZEBO_R + .2, GAZEBO_R + .2, 1, GAZEBO_POSTS), wood); deck.position.set(g.x, floor - .3, g.z); G.add(deck);
  for (let k = 0; k < GAZEBO_POSTS; k++) {
    const a = k / GAZEBO_POSTS * Math.PI * 2, post = new THREE.Mesh(new THREE.BoxGeometry(.15, 2.4, .15), wood);
    post.position.set(g.x + Math.cos(a) * GAZEBO_R, floor + 1.4, g.z + Math.sin(a) * GAZEBO_R); G.add(post);
  }
  const cap = new THREE.Mesh(new THREE.ConeGeometry(GAZEBO_R + .6, 1.6, GAZEBO_POSTS), roof); cap.position.set(g.x, floor + 3.4, g.z); G.add(cap);
  const bench = new THREE.Mesh(new THREE.CylinderGeometry(GAZEBO_R - .3, GAZEBO_R - .3, .1, GAZEBO_POSTS, 1, true), wood); bench.position.set(g.x, floor + .65, g.z); G.add(bench);
});
