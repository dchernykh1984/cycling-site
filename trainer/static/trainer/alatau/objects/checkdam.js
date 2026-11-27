'use strict';
/* A mudflow dam of concrete across a valley, the route's road running through it in a gallery: along its crest
   (lm.crest, [[latitude, longitude], ...]) lm.thick metres thick (20 unless given), its top level lm.h metres over
   the road where the road passes through (12 unless given), down to the ground -- ending where the valley's sides
   rise over it --; over the road an opening GALLERY_M high between upright walls beyond its edges, the dam over it;
   on its upstream face, towards the route's way on, a row of white posts. */
const GALLERY_M = 5.5, GALLERY_SIDE_M = 1.5, CHECKDAM_POST_EVERY = 5, CHECKDAM_STEP = 1.5;
addObject('checkdam', (G, lm, T, { land }) => {
  G.userData.spread = true; G.position.set(lm.x, 0, lm.z); // it stands each part on the land itself
  const W = T.route.width, thick = lm.thick || 20, line = lm.crest.map(p => { const q = proj(p[0], p[1], T.origin); return { x: q.x, z: q.z }; });
  // where the road passes under it: the crest's point nearest the route, the road's height there
  let at = null;
  along(line, 2).forEach(p => { const n = routeNearest(T, p.x, p.z); if (!at || n.d < at.d) at = { d: n.d, y: n.y, s: n.s }; });
  const top = at.y + (lm.h || 12), floor = at.y + GALLERY_M, way = sampleAt(T, at.s, {}), pts = along(line, CHECKDAM_STEP);
  // each step along the crest: its two corners across (downstream, upstream), each down to the ground; a step whose
  // corners come over the road is the opening; one whose ground rises over the top is in the valley's side
  const cols = pts.map((p, i) => {
    const q = pts[Math.min(i + 1, pts.length - 1)], r = pts[Math.max(i - 1, 0)], dx = q.x - r.x, dz = q.z - r.z, L = Math.hypot(dx, dz) || 1;
    let nx = -dz / L, nz = dx / L; if (nx * way.tx + nz * way.tz < 0) { nx = -nx; nz = -nz; } // n: upstream, the way on
    const c = [-1, 1].map(k => { const x = p.x + nx * thick / 2 * k, z = p.z + nz * thick / 2 * k; return { x, z, y: land(x, z) - 1 }; });
    const open = c.some(v => routeGap(T, v.x, v.z) < W / 2 + GALLERY_SIDE_M) || routeGap(T, p.x, p.z) < W / 2 + GALLERY_SIDE_M;
    return { p, c, open, gone: c.every(v => v.y >= top - .5) };
  });
  const P = [], I = [];
  const quad = (a, b, c, d) => { const k = P.length / 3; [a, b, c, d].forEach(v => P.push(v[0] - lm.x, v[1], v[2] - lm.z)); I.push(k, k + 1, k + 2, k, k + 2, k + 3); };
  const corner = (v, y) => [v.x, y, v.z];
  // the body in runs of steps between the opening and the valley's sides, each closed at its ends by an upright face
  let run = [];
  const flush = () => {
    if (run.length > 1) {
      for (let i = 0; i + 1 < run.length; i++) {
        const [a0, a1] = run[i].c, [b0, b1] = run[i + 1].c;
        quad(corner(a0, top), corner(a1, top), corner(b1, top), corner(b0, top));
        quad(corner(a0, Math.min(a0.y, top)), corner(a0, top), corner(b0, top), corner(b0, Math.min(b0.y, top)));
        quad(corner(a1, top), corner(a1, Math.min(a1.y, top)), corner(b1, Math.min(b1.y, top)), corner(b1, top));
      }
      [run[0], run[run.length - 1]].forEach(({ c: [a, b] }) => quad(corner(a, Math.min(a.y, top)), corner(b, Math.min(b.y, top)), corner(b, top), corner(a, top)));
    }
    run = [];
  };
  cols.forEach(col => { if (col.open || col.gone) flush(); else run.push(col); });
  flush();
  // over the opening, the dam from the gallery's ceiling to the top, its walls upright at the opening's ends
  const open = cols.map((col, i) => col.open ? i : -1).filter(i => i >= 0);
  if (open.length) {
    const a = cols[Math.max(0, open[0] - 1)], b = cols[Math.min(cols.length - 1, open[open.length - 1] + 1)];
    const [a0, a1] = a.c, [b0, b1] = b.c;
    quad(corner(a0, top), corner(a1, top), corner(b1, top), corner(b0, top));
    quad(corner(a0, floor), corner(a1, floor), corner(b1, floor), corner(b0, floor));
    quad(corner(a0, floor), corner(a0, top), corner(b0, top), corner(b0, floor));
    quad(corner(a1, top), corner(a1, floor), corner(b1, floor), corner(b1, top));
  }
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(P, 3)); g.setIndex(I); g.computeVertexNormals();
  G.add(new THREE.Mesh(g, new THREE.MeshLambertMaterial({ color: lm.c || 0xa9a59b, side: THREE.DoubleSide })));
  // the white posts along its upstream edge, where it stands over the valley
  const white = new THREE.MeshLambertMaterial({ color: 0xe9e7e0 });
  cols.forEach((col, i) => {
    if (i % Math.round(CHECKDAM_POST_EVERY / CHECKDAM_STEP) || col.open || col.gone || col.c[1].y > top - 3) return;
    const m = new THREE.Mesh(new THREE.BoxGeometry(1.2, 2.6, 1.2), white); m.position.set(col.c[1].x - lm.x, top + 1.3, col.c[1].z - lm.z); G.add(m);
  });
});
