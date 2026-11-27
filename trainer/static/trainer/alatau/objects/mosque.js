'use strict';
/* A mosque as OpenStreetMap outlines it (lm.outline, [[latitude, longitude], ...]): its hall's walls lm.h metres tall
   (8 unless given) of lm.c, a drum and a dome of lm.dome over the hall's middle with a crescent on its spire, and a
   minaret lm.minaret metres tall (26 unless given) with its balcony and a pointed cap at the hall's corner nearest the
   route. */
addObject('mosque', (G, lm, T, { lam, box, cyl, sink }) => {
  let ring = lm.outline.map(p => { const q = proj(p[0], p[1], T.origin); return [q.x - lm.x, q.z - lm.z]; });
  if (ring.length > 2 && ring[0][0] === ring[ring.length - 1][0] && ring[0][1] === ring[ring.length - 1][1]) ring.pop();
  let area = 0; ring.forEach((p, i) => { const q = ring[(i + 1) % ring.length]; area += p[0] * q[1] - q[0] * p[1]; });
  if (area > 0) ring = ring.reverse(); // the walls' faces outwards, as js/osm.js draws a building
  const H = lm.h || 8, wall = new THREE.Color(lm.c || '#f1ede3'), pos = [], col = [], base = -2 - sink;
  const push = (x, y, z) => { pos.push(x, y, z); col.push(wall.r, wall.g, wall.b); };
  ring.forEach((p, i) => {
    const q = ring[(i + 1) % ring.length];
    push(p[0], base, p[1]); push(q[0], base, q[1]); push(q[0], H, q[1]);
    push(p[0], base, p[1]); push(q[0], H, q[1]); push(p[0], H, p[1]);
  });
  THREE.ShapeUtils.triangulateShape(ring.map(p => new THREE.Vector2(p[0], p[1])), []).forEach(t => t.slice().reverse().forEach(k => push(ring[k][0], H, ring[k][1])));
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3)); g.computeVertexNormals();
  G.add(new THREE.Mesh(g, new THREE.MeshLambertMaterial({ vertexColors: true })));
  // the dome over the middle of the hall, as wide as a third of its narrower side
  const cx = ring.reduce((a, p) => a + p[0], 0) / ring.length, cz = ring.reduce((a, p) => a + p[1], 0) / ring.length;
  const xs = ring.map(p => p[0]), zs = ring.map(p => p[1]), R = Math.max(3, Math.min(Math.max(...xs) - Math.min(...xs), Math.max(...zs) - Math.min(...zs)) / 3);
  const dome = lam(lm.dome || 0x2f8fa8), gold = lam(0xd9b44a);
  cyl(R * .92, R * .92, R * .45, lm.c || 0xf1ede3, cx, H, cz, 24);
  const cap = new THREE.Mesh(new THREE.SphereGeometry(R, 24, 12, 0, Math.PI * 2, 0, Math.PI / 2), dome); cap.position.set(cx, H + R * .45, cz); G.add(cap);
  cyl(.12, .12, R * .5, gold, cx, H + R * 1.45, cz, 6);
  const moon = new THREE.Mesh(new THREE.TorusGeometry(R * .14, R * .035, 6, 16, Math.PI * 1.4), gold); moon.position.set(cx, H + R * 2.05, cz); G.add(moon);
  // the minaret at the hall's corner nearest the route
  const o = sampleAt(T, lm.s, {}), rx = o.x - lm.x, rz = o.z - lm.z;
  const [mx, mz] = ring.reduce((a, p) => Math.hypot(p[0] - rx, p[1] - rz) < Math.hypot(a[0] - rx, a[1] - rz) ? p : a);
  const M = lm.minaret || 26, white = lm.c || 0xf1ede3;
  cyl(1.4, 1.6, M * .7, white, mx, 0, mz, 12);
  cyl(2.1, 1.5, .9, white, mx, M * .7, mz, 12);
  cyl(1.1, 1.2, M * .18, white, mx, M * .7 + .9, mz, 12);
  cyl(.05, 1.25, M * .12, dome, mx, M * .88 + .9, mz, 12);
  cyl(.06, .06, 1.6, gold, mx, M + .9, mz, 6);
});
