'use strict';
/* A filling station: its canopy as OpenStreetMap outlines it (lm.outline, [[latitude, longitude], ...]) FUEL_ROOF_M
   over the ground, its edge in the brand's colour lm.c, on pillars over two pump islands; and by the road, at the
   outline's corner nearest the route, its pylon with the name (lm.sign) on both faces. */
const FUEL_ROOF_M = 5.2;
addObject('fuel', (G, lm, T, { lam, box, cyl, sink }) => {
  let ring = lm.outline.map(p => { const q = proj(p[0], p[1], T.origin); return [q.x - lm.x, q.z - lm.z]; });
  if (ring.length > 2 && ring[0][0] === ring[ring.length - 1][0] && ring[0][1] === ring[ring.length - 1][1]) ring.pop();
  const brand = lam(lm.c || 0x1f5fa8), white = lam(0xf2f2ef);
  // the roof: the outline lifted, its slab white and its edge the brand's
  const shape = new THREE.Shape(ring.map(p => new THREE.Vector2(p[0], -p[1])));
  const slab = new THREE.Mesh(new THREE.ExtrudeGeometry(shape, { depth: .9, bevelEnabled: false }), [white, brand]);
  slab.rotation.x = -Math.PI / 2; slab.position.y = FUEL_ROOF_M; G.add(slab);
  // pillars and pumps along the outline's long axis
  const cx = ring.reduce((a, p) => a + p[0], 0) / ring.length, cz = ring.reduce((a, p) => a + p[1], 0) / ring.length;
  const far = ring.reduce((a, p) => Math.hypot(p[0] - cx, p[1] - cz) > Math.hypot(a[0] - cx, a[1] - cz) ? p : a);
  const ax = far[0] - cx, az = far[1] - cz, al = Math.hypot(ax, az) || 1, ux = ax / al, uz = az / al, turn = Math.atan2(ux, uz);
  [-.45, .45].forEach(k => {
    const x = cx + ux * al * k, z = cz + uz * al * k;
    cyl(.35, .35, FUEL_ROOF_M, white, x, 0, z, 10);
    const island = box(1.2, .25, 5, 0xbfbfbf, x, 0, z); island.rotation.y = turn;
    [-1.3, 1.3].forEach(d => { const pump = box(.7, 1.8, .9, brand, x + ux * d, .25, z + uz * d); pump.rotation.y = turn; });
  });
  // the pylon by the road, the name on both faces
  const o = sampleAt(T, lm.s, {}), rx = o.x - lm.x, rz = o.z - lm.z;
  const [px, pz] = ring.reduce((a, p) => Math.hypot(p[0] - rx, p[1] - rz) < Math.hypot(a[0] - rx, a[1] - rz) ? p : a);
  const tex = canvasTex(512, 1024, (c, w, h) => {
    c.fillStyle = '#' + new THREE.Color(lm.c || 0x1f5fa8).getHexString(); c.fillRect(0, 0, w, h);
    c.fillStyle = '#ffffff'; c.textAlign = 'center'; c.textBaseline = 'middle';
    let size = 120; c.font = '700 ' + size + 'px Golos Text, sans-serif';
    while (c.measureText(lm.sign || '').width > w * .9 && size > 20) { size *= .92; c.font = '700 ' + size + 'px Golos Text, sans-serif'; }
    c.fillText(lm.sign || '', w / 2, h * .2);
    c.fillStyle = '#f4f4f0'; for (let k = 0; k < 4; k++) c.fillRect(w * .12, h * (.38 + k * .14), w * .76, h * .1);
  });
  const face = new THREE.MeshBasicMaterial({ map: tex });
  const pylon = new THREE.Mesh(new THREE.BoxGeometry(2.2, 6.4 + sink, .5), [brand, brand, brand, brand, face, face]);
  pylon.position.set(px, (6.4 - sink) / 2, pz); G.add(pylon);
  pylon.rotation.y = Math.atan2(o.tx, o.tz); // across the road: a face to the riders coming each way
});
