'use strict';
/* A checkpoint's lift gate across the route and its guard's booth, both on the side of the road lm.side gives -- right
   or left of the riders on its first pass, the way up (OpenStreetMap's outline put the booth in the road) --: the
   gate's post beyond the road's edge, its red and white arm raised -- open, a ride does not stop for it --, and the
   booth (lm.booth, its outline: only its size is taken) GATE_BOOTH_M tall beside it, standing at the road's level or
   the land's highest under it, its walls down into the land. */
const GATE_BOOTH_M = 2.8, GATE_ARM_STRIPE = 1;
addObject('gate', (G, lm, T, { lam, box, cyl, land }) => {
  G.userData.spread = true;
  const W = T.route.width;
  // the route's first pass by it: the nearest of its points, the earliest of those within a metre of that
  let best = Infinity; const d2 = i => (T.X[i] - lm.x) ** 2 + (T.Z[i] - lm.z) ** 2;
  for (let i = 0; i < T.N; i++) best = Math.min(best, d2(i));
  let first = 0; while (Math.sqrt(d2(first)) > Math.sqrt(best) + 1) first++;
  const o = sampleAt(T, T.D[first], {}), side = lm.side === 'left' ? -1 : 1;
  G.position.set(lm.x, 0, lm.z);
  const ring = lm.booth.map(p => { const q = proj(p[0], p[1], T.origin); return [q.x, q.z]; });
  const xs = ring.map(p => p[0]), zs = ring.map(p => p[1]), bw = Math.max(2.4, Math.min(4, Math.max(...xs) - Math.min(...xs))), bd = Math.max(2.4, Math.min(4, Math.max(...zs) - Math.min(...zs)));
  // the booth beyond the shoulder, its long side to the road, a few metres before the gate
  const off = W / 2 + 2.5 + bd / 2, bx = o.x + o.rx * off * side - o.tx * 4, bz = o.z + o.rz * off * side - o.tz * 4;
  let by = o.y; for (const [a, b] of [[-1, -1], [-1, 1], [1, -1], [1, 1]]) by = Math.max(by, land(bx + o.tx * bw / 2 * a + o.rx * bd / 2 * b, bz + o.tz * bw / 2 * a + o.rz * bd / 2 * b));
  const white = lam(0xe8e6df), glass = lam(0x2f3f4a), roof = lam(0x4f6b4a);
  const booth = new THREE.Group(); booth.position.set(bx - lm.x, by, bz - lm.z); booth.rotation.y = Math.atan2(o.tx, o.tz); G.add(booth);
  [[0, -2, 0, bw, GATE_BOOTH_M + 2, bd, white], [0, GATE_BOOTH_M, 0, bw + .4, .25, bd + .4, roof]].forEach(([x, y, z, w, h, d, m]) => {
    const b = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m); b.position.set(x, y + h / 2, z); booth.add(b);
  });
  [[0, bd / 2 + .01, 0], [0, -bd / 2 - .01, Math.PI], [bw / 2 + .01, 0, Math.PI / 2], [-bw / 2 - .01, 0, -Math.PI / 2]].forEach(([x, z, r]) => {
    const w = new THREE.Mesh(new THREE.PlaneGeometry(Math.min(bw, bd) * .6, .9), glass); w.position.set(x, 1.5, z); w.rotation.y = r; booth.add(w);
  });
  // the gate: its post beyond the edge on the booth's side, the arm raised along the post
  const px = o.x + o.rx * side * (W / 2 + .8), pz = o.z + o.rz * side * (W / 2 + .8), py = land(px, pz);
  const post = new THREE.Mesh(new THREE.BoxGeometry(.35, 1.4, .35), white); post.position.set(px - lm.x, py + .5, pz - lm.z); G.add(post);
  const arm = new THREE.Group(); arm.position.set(px - lm.x, py + 1.1, pz - lm.z); G.add(arm);
  const red = lam(0xc3323b), len = W + .5;
  for (let k = 0; k * GATE_ARM_STRIPE < len; k++) {
    const piece = new THREE.Mesh(new THREE.BoxGeometry(.12, GATE_ARM_STRIPE, .08), k % 2 ? white : red); piece.position.y = (k + .5) * GATE_ARM_STRIPE; arm.add(piece);
  }
  arm.rotation.y = Math.atan2(o.tx, o.tz); arm.rotation.x = -.08; // up, a little back from the road
});
