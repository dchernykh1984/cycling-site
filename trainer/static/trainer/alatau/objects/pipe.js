'use strict';
/* A pipeline on the land, as OpenStreetMap draws it (lm.line, [[latitude, longitude], ...]): a steel tube lm.d metres
   across (1 unless given) on low supports every PIPE_SUPPORT_M, PIPE_LIFT_M over the ground under it. Where the route's
   road crosses it the tube runs on unbroken under a bridge, as the BAO pipe does at each of its crossings: down under
   the deck within PIPE_RAMP_M of the road, the bridge's faces along the road's edges from below the tube up to their
   parapets. */
const PIPE_STEP_M = 3, PIPE_SUPPORT_M = 12, PIPE_LIFT_M = .5, PIPE_DECK_M = .8, PIPE_RAMP_M = 4, PIPE_BRIDGE_M = 1.5;
addObject('pipe', (G, lm, T, { land }) => {
  G.userData.spread = true; G.position.set(lm.x, 0, lm.z);
  const R = (lm.d || 1) / 2, W = T.route.width, clear = W / 2 + R + 1;
  const line = along(lm.line.map(p => { const q = proj(p[0], p[1], T.origin); return { x: q.x, z: q.z }; }), PIPE_STEP_M);
  const steel = new THREE.MeshLambertMaterial({ color: lm.c || 0x8e9497 }), concrete = new THREE.MeshLambertMaterial({ color: 0xb9b4a8, side: THREE.DoubleSide });
  // on its supports, else under the road's deck, coming up out of it across PIPE_RAMP_M
  const pts = line.map(p => {
    const gap = routeGap(T, p.x, p.z), up = land(p.x, p.z) + PIPE_LIFT_M + R, under = routeNearest(T, p.x, p.z).y - PIPE_DECK_M - R;
    const y = Math.min(up, under + (up - under) * clamp((gap - clear) / PIPE_RAMP_M, 0, 1));
    return { x: p.x, z: p.z, gap, raised: y >= up - 1e-6, v: new THREE.Vector3(p.x - lm.x, y, p.z - lm.z) };
  });
  const path = new THREE.CurvePath();
  for (let i = 0; i + 1 < pts.length; i++) path.add(new THREE.LineCurve3(pts[i].v, pts[i + 1].v));
  G.add(new THREE.Mesh(new THREE.TubeGeometry(path, pts.length * 2, R, 10, false), steel));
  for (let i = 0; i < pts.length; i += Math.round(PIPE_SUPPORT_M / PIPE_STEP_M)) {
    if (!pts[i].raised) continue;
    const p = pts[i].v, h = PIPE_LIFT_M + 1, s = new THREE.Mesh(new THREE.BoxGeometry(R * 1.6, h, .8), concrete);
    const q = pts[Math.min(i + 1, pts.length - 1)].v, r = pts[Math.max(i - 1, 0)].v;
    s.position.set(p.x, p.y - R - PIPE_LIFT_M - 1 + h / 2, p.z); s.rotation.y = Math.atan2(q.x - r.x, q.z - r.z); G.add(s);
  }
  // each crossing's bridge: where the road passes over the tube (its first pass, a road ridden back being the same road)
  const P = [], I = [], o = {};
  let run = [];
  const bridge = () => {
    if (!run.length) return;
    const ss = run.map(p => T.D[firstPassAt(T, p.x, p.z)]), s0 = Math.min(...ss) - R - PIPE_BRIDGE_M, s1 = Math.max(...ss) + R + PIPE_BRIDGE_M;
    for (const k of [-1, 1]) {
      const face = [];
      for (let s = s0; s <= s1 + 1e-6; s += 1) {
        sampleAt(T, s, o);
        face.push({ x: o.x + o.rx * (W / 2 + .3) * k - lm.x, z: o.z + o.rz * (W / 2 + .3) * k - lm.z, y0: o.y - PIPE_DECK_M - 2 * R - .3, y1: o.y + 1.05 });
      }
      wallOf(P, I, face, .35);
    }
    run = [];
  };
  pts.forEach(p => { if (p.gap < W / 2 + R) run.push(p); else bridge(); });
  bridge();
  meshOf(G, P, I, concrete, 'pipe bridges');
});
