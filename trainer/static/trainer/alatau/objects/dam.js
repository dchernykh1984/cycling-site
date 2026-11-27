'use strict';
/* An earth dam across a gorge, along its crest as OpenStreetMap draws it (lm.crest, [[latitude, longitude], ...]),
   lm.h metres over the ground at its place: a crest lm.wide metres wide (DAM_CREST unless given), its faces falling
   at two to one to the gorge's floor and running lm.into metres into its walls (DAM_INTO_WALLS unless given) --
   drawn only where it stands over the land -- a road along the crest between parapets, and a stair up the middle of the face towards the route, in flights between
   landings, unless lm.stair is false (Medeu's has one, Big Almaty Lake's none). Its faces fall at lm.slope to one
   (DAM_SLOPE unless given), drawn every lm.step metres (DAM_STEP); a dam the route climbs over (lm.road, Ayusai's in
   five hairpins up its face) keeps its surface under the route's road and shoulders -- the road on benches cut in
   it -- and has no road of its own on the crest: the route is that road. One with lm.taper falls at its slope past
   its crest's ends too, onto a valley SRTM has from before it was built, not to a wall hanging over it. */
const DAM_SLOPE = 2, DAM_CREST = 50, DAM_STEP = 8, DAM_INTO_WALLS = 160, DAM_BANK_M = 10;
addObject('dam', (G, lm, T, { lam, box, land }) => {
  G.userData.spread = true; // it lies on the land it crosses, its surface a metre under it wherever it is not over it
  const ends = [lm.crest[0], lm.crest[lm.crest.length - 1]].map(p => { const q = proj(p[0], p[1], T.origin); return [q.x - lm.x, q.z - lm.z]; });
  let ux = ends[1][0] - ends[0][0], uz = ends[1][1] - ends[0][1]; const len = Math.hypot(ux, uz) || 1; ux /= len; uz /= len;
  // the face towards the route's end, where the stair climbs
  const o = sampleAt(T, T.L, {}), nx0 = -uz, nz0 = ux, toward = (o.x - lm.x) * nx0 + (o.z - lm.z) * nz0 > 0 ? 1 : -1, nx = nx0 * toward, nz = nz0 * toward;
  const mx = (ends[0][0] + ends[1][0]) / 2, mz = (ends[0][1] + ends[1][1]) / 2, H = lm.h || 150, y0 = G.position.y, CREST = lm.wide || DAM_CREST;
  const put = (a, b) => [mx + ux * a + nx * b, mz + uz * a + nz * b]; // a along the crest, b out towards the route
  const ground = (a, b) => { const [x, z] = put(a, b); return land(lm.x + x, lm.z + z) - y0; };
  const SLOPE = lm.slope || DAM_SLOPE, STEP = lm.step || DAM_STEP, W = T.route.width;
  const face = (b, a = 0) => H - Math.max(0, Math.abs(b) - CREST / 2) / SLOPE - (lm.taper ? Math.max(0, Math.abs(a) - len / 2) / SLOPE : 0);
  // the dam as a surface over the land: its height where it stands over the ground, a metre under the ground elsewhere
  const half = len / 2 + (lm.into != null ? lm.into : DAM_INTO_WALLS), wide = CREST / 2 + SLOPE * H + 40, na = Math.ceil(2 * half / STEP), nb = Math.ceil(2 * wide / STEP);
  const pos = [], col = [], idx = [], c = new THREE.Color(), earth = new THREE.Color(0x7d8456), top = new THREE.Color(0xa9a48a);
  for (let i = 0; i <= na; i++) for (let j = 0; j <= nb; j++) {
    const a = -half + 2 * half * i / na, b = -wide + 2 * wide * j / nb, g = ground(a, b), y = face(b, a), [x, z] = put(a, b);
    let at = y > g ? y : g - 1;
    if (lm.road) { // the road's bench: under it, and a bank up to the face over DAM_BANK_M beyond its shoulder
      const n = routeNearest(T, lm.x + x, lm.z + z), bench = n.y - 1.3 - y0, k = clamp((n.d - W / 2 - 2.5) / DAM_BANK_M, 0, 1);
      if (at > bench) at = bench + (at - bench) * k * k * (3 - 2 * k);
    }
    pos.push(x, at, z); c.copy(Math.abs(b) <= CREST / 2 ? top : earth); col.push(c.r, c.g, c.b);
  }
  // wound to face up whichever face is towards the route: turned the other way, Ayusai's lay dark, lit from beneath
  for (let i = 0; i < na; i++) for (let j = 0; j < nb; j++) { const p = i * (nb + 1) + j, q = p + nb + 1; if (toward > 0) idx.push(p, p + 1, q, q, p + 1, q + 1); else idx.push(p, q, p + 1, q, q + 1, p + 1); }
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
  g.setIndex(idx); g.computeVertexNormals(); G.add(new THREE.Mesh(g, new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide })));
  const along = Math.atan2(ux, uz), crestY = H + .5;
  if (lm.road) return; // the route is its road
  // the crest's road between its parapets, as long as the crest OpenStreetMap draws
  [[0, 14, 1, 0x8f8c84], [-7.5, 1, 1.2, 0xe6e3dc], [7.5, 1, 1.2, 0xe6e3dc]].forEach(([b, w, h, cl]) => {
    const [x, z] = put(0, b), m = box(w, h, len, cl, x, crestY, z); m.rotation.y = along;
  });
  if (lm.stair === false) return;
  // the stair: flights up the face from where it leaves the ground to the crest, a landing between each two
  let from = CREST / 2 + SLOPE * H; while (from > CREST / 2 && face(from) < ground(0, from)) from -= 2;
  const FLIGHTS = 12, run = (from - CREST / 2) / FLIGHTS, white = lam(0xe6e3dc), green = lam(0x5f6b3c), turn = Math.atan2(nx, nz);
  for (let k = 0; k < FLIGHTS && run > 8; k++) {
    const b0 = from - k * run, b1 = b0 - run + 6, ya = face(b0), yb = face(b1), span = Math.hypot(b0 - b1, yb - ya);
    [[0, 8, white, .8], [-6, 2.5, green, 1], [6, 2.5, green, 1]].forEach(([side, w, mat, lift]) => {
      const [x, z] = put(side, (b0 + b1) / 2), m = new THREE.Mesh(new THREE.BoxGeometry(w, 1.2, span), mat);
      m.position.set(x, (ya + yb) / 2 + lift, z); m.rotation.order = 'YXZ'; m.rotation.y = turn; m.rotation.x = Math.atan2(yb - ya, b0 - b1); G.add(m);
    });
    const [lx, lz] = put(0, b1 - 3), landing = box(12, 1, 6, white, lx, face(b1 - 3), lz); landing.rotation.y = turn;
  }
});
