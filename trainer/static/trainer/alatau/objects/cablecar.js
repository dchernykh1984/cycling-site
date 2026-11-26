'use strict';
/* A gondola lift: its two stations, its pylons and two cables along lm.line -- OpenStreetMap's way, [[latitude,
   longitude], ...], its first the station the sight stands at and its last the other -- and lm.cabins cabins hanging
   still on the cables, half going up and half coming down. Each part stands on the land under it (kit.land). */
addObject('cablecar', (G, lm, T, { lam, box, cyl, land }) => {
  G.userData.spread = true; // its parts stand each on its own land, the stations and the pylons (userData.stands)
  // the land under a part: the lowest under its footprint, r metres every way, so it stands on a slope
  const low = (x, z, r) => Math.min(...[[0, 0], [r, r], [r, -r], [-r, r], [-r, -r]].map(([a, b]) => land(x + a, z + b))) - G.position.y;
  const last = lm.line.length - 1, grey = lam(0x9ba0a4);
  const pts = lm.line.map((p, i) => { const q = proj(p[0], p[1], T.origin); return { x: q.x - lm.x, z: q.z - lm.z, g: low(q.x, q.z, i === 0 || i === last ? 14 : 1.2) }; });
  pts.forEach((p, i) => { p.top = p.g + (i === 0 || i === last ? 9 : (lm.pylon || 26)); });
  const dir = (i) => { const a = pts[Math.max(0, i - 1)], b = pts[Math.min(last, i + 1)], L = Math.hypot(b.x - a.x, b.z - a.z) || 1; return { x: (b.x - a.x) / L, z: (b.z - a.z) / L }; };
  // the stations, long along the line; the pylons, tapering to a cross-beam that carries both cables
  [0, last].forEach(i => {
    const d = dir(i), st = box(12, 10, 26, 0xd9d4c8, pts[i].x, pts[i].g - .5, pts[i].z);
    st.rotation.y = Math.atan2(d.x, d.z); st.userData.stands = true;
  });
  for (let i = 1; i < last; i++) {
    const p = pts[i], d = dir(i);
    cyl(.45, 1.1, p.top - p.g, grey, p.x, p.g - .3, p.z, 6).userData.stands = true;
    const beam = box(6.4, .7, .7, grey, p.x, p.top - .4, p.z); beam.rotation.y = Math.atan2(d.x, d.z);
  }
  // two cables 5.2 m apart, sagging between their supports; the cabins spread along the way up and the way down
  const wires = [], spots = [];
  for (const side of [-2.6, 2.6]) {
    const line = [];
    for (let i = 0; i < last; i++) {
      const a = pts[i], b = pts[i + 1], da = dir(i), db = dir(i + 1), span = Math.hypot(b.x - a.x, b.z - a.z), sag = Math.min(30, span * .035);
      for (let k = 0; k <= 12; k++) {
        const f = k / 12, nx = (da.z * (1 - f) + db.z * f) * side, nz = -(da.x * (1 - f) + db.x * f) * side;
        line.push(new THREE.Vector3(a.x + (b.x - a.x) * f + nx, a.top + (b.top - a.top) * f - sag * 4 * f * (1 - f), a.z + (b.z - a.z) * f + nz));
      }
    }
    for (let i = 0; i + 1 < line.length; i++) wires.push(line[i], line[i + 1]);
    spots.push(line);
  }
  const g = new THREE.BufferGeometry().setFromPoints(wires);
  G.add(new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: 0x3b3e42 })));
  const n = lm.cabins || 16, red = lam(0xc8372f);
  for (let k = 0; k < n; k++) {
    const line = spots[k % 2], at = line[Math.min(line.length - 1, Math.round((k + .5) / n * (line.length - 1)))];
    box(2.2, 2.4, 2.4, red, at.x, at.y - 4.2, at.z);
    cyl(.06, .06, 1.8, 0x3b3e42, at.x, at.y - 1.9, at.z, 4);
  }
});
