'use strict';
/* A checkpoint's lift gate across the route and its guard's booth: the gate's post beyond the road's edge on the
   booth's side, its red and white arm raised -- open, a ride does not stop for it --, and the booth as OpenStreetMap
   outlines it (lm.booth, [[latitude, longitude], ...]), GATE_BOOTH_M tall with its windows round. */
const GATE_BOOTH_M = 2.8, GATE_ARM_STRIPE = 1;
addObject('gate', (G, lm, T, { lam, box, cyl, land }) => {
  G.userData.spread = true;
  const n = routeNearest(T, lm.x, lm.z), o = sampleAt(T, n.s, {}), W = T.route.width;
  G.position.set(lm.x, 0, lm.z);
  // the booth's middle, and the road's side it stands on
  const ring = lm.booth.map(p => { const q = proj(p[0], p[1], T.origin); return [q.x, q.z]; });
  const bx = ring.reduce((a, p) => a + p[0], 0) / ring.length, bz = ring.reduce((a, p) => a + p[1], 0) / ring.length;
  const side = (bx - o.x) * o.rx + (bz - o.z) * o.rz > 0 ? 1 : -1;
  const xs = ring.map(p => p[0]), zs = ring.map(p => p[1]), bw = Math.max(2.4, Math.max(...xs) - Math.min(...xs)), bd = Math.max(2.4, Math.max(...zs) - Math.min(...zs));
  const by = land(bx, bz), white = lam(0xe8e6df), glass = lam(0x2f3f4a), roof = lam(0x4f6b4a);
  const booth = new THREE.Group(); booth.position.set(bx - lm.x, by, bz - lm.z); G.add(booth);
  [[0, -.5, 0, bw, GATE_BOOTH_M + .5, bd, white], [0, GATE_BOOTH_M, 0, bw + .4, .25, bd + .4, roof]].forEach(([x, y, z, w, h, d, m]) => {
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
