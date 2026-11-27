'use strict';
/* A pipeline on the land, as OpenStreetMap draws it (lm.line, [[latitude, longitude], ...]): a steel tube lm.d metres
   across (1 unless given) on low supports every PIPE_SUPPORT_M, PIPE_LIFT_M over the ground under it -- going under
   the route's road where it crosses it. */
const PIPE_STEP_M = 3, PIPE_SUPPORT_M = 12, PIPE_LIFT_M = .5;
addObject('pipe', (G, lm, T, { land }) => {
  G.userData.spread = true; G.position.set(lm.x, 0, lm.z);
  const R = (lm.d || 1) / 2, W = T.route.width;
  const line = along(lm.line.map(p => { const q = proj(p[0], p[1], T.origin); return { x: q.x, z: q.z }; }), PIPE_STEP_M);
  const steel = new THREE.MeshLambertMaterial({ color: lm.c || 0x8e9497 }), concrete = new THREE.MeshLambertMaterial({ color: 0xb9b4a8 });
  const runs = []; let run = [];
  line.forEach(p => {
    if (routeGap(T, p.x, p.z) < W / 2 + R + 1) { if (run.length > 1) runs.push(run); run = []; return; } // under the road
    run.push(new THREE.Vector3(p.x - lm.x, land(p.x, p.z) + PIPE_LIFT_M + R, p.z - lm.z));
  });
  if (run.length > 1) runs.push(run);
  runs.forEach(pts => {
    const path = new THREE.CurvePath();
    for (let i = 0; i + 1 < pts.length; i++) path.add(new THREE.LineCurve3(pts[i], pts[i + 1]));
    G.add(new THREE.Mesh(new THREE.TubeGeometry(path, pts.length * 2, R, 10, false), steel));
    for (let i = 0; i < pts.length; i += Math.round(PIPE_SUPPORT_M / PIPE_STEP_M)) {
      const p = pts[i], h = PIPE_LIFT_M + 1, s = new THREE.Mesh(new THREE.BoxGeometry(R * 1.6, h, .8), concrete);
      const q = pts[Math.min(i + 1, pts.length - 1)], r = pts[Math.max(i - 1, 0)];
      s.position.set(p.x, p.y - R - PIPE_LIFT_M - 1 + h / 2, p.z); s.rotation.y = Math.atan2(q.x - r.x, q.z - r.z); G.add(s);
    }
  });
});
