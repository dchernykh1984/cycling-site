'use strict';
/* Ski jumps on a hillside, each along lm.jumps' [top latitude, longitude, foot latitude, longitude, inrun height]:
   OpenStreetMap's pitch from its high end to its low one. The inrun runs from a tower that high over the land down
   to the take-off, a third of the way; the landing hill lies on the land from there to the foot, widening to the
   outrun. Each part stands on the land under it (kit.land). */
addObject('skijump', (G, lm, T, { lam, box, land }) => {
  G.userData.spread = true; // its parts stand each on its own land, the inrun's legs and tower (userData.stands)
  const white = new THREE.MeshLambertMaterial({ color: 0xe9ece6, side: THREE.DoubleSide }), steel = lam(0x8c9298);
  lm.jumps.forEach(([la0, lo0, la1, lo1, inrun]) => {
    const a = proj(la0, lo0, T.origin), b = proj(la1, lo1, T.origin), L = Math.hypot(b.x - a.x, b.z - a.z), ux = (b.x - a.x) / L, uz = (b.z - a.z) / L;
    const at = s => ({ x: a.x + ux * s - lm.x, z: a.z + uz * s - lm.z, g: land(a.x + ux * s, a.z + uz * s) - G.position.y });
    const takeoff = L * .32, top = at(0), lip = at(takeoff), y0 = top.g + inrun, y1 = lip.g + 3;
    // the landing hill: a band on the land, 12 m wide at the take-off and 34 m at the foot
    const P = [], I = [];
    for (let s = takeoff, i = 0; s <= L + 1e-6; s += 5, i++) {
      const p = at(s), w = (12 + 22 * (s - takeoff) / (L - takeoff)) / 2;
      P.push(p.x - uz * w, p.g + .3, p.z + ux * w, p.x + uz * w, p.g + .3, p.z - ux * w);
      if (i) { const v = i * 2; I.push(v - 2, v - 1, v, v - 1, v + 1, v); }
    }
    const hill = new THREE.BufferGeometry(); hill.setAttribute('position', new THREE.Float32BufferAttribute(P, 3)); hill.setIndex(I); hill.computeVertexNormals();
    G.add(new THREE.Mesh(hill, white));
    // the inrun: a ramp 5 m wide from the tower's top to the take-off, on legs every 12 m
    const len = Math.hypot(takeoff, y0 - y1), ramp = new THREE.Mesh(new THREE.BoxGeometry(5, .8, len), white);
    ramp.position.set((top.x + lip.x) / 2, (y0 + y1) / 2, (top.z + lip.z) / 2);
    ramp.rotation.order = 'YXZ'; ramp.rotation.y = Math.atan2(ux, uz); ramp.rotation.x = Math.atan2(y0 - y1, takeoff); G.add(ramp);
    for (let s = 6; s < takeoff - 3; s += 12) {
      const p = at(s), y = y0 + (y1 - y0) * s / takeoff;
      if (y - p.g > 1) box(1.2, y - p.g + .3, 1.2, steel, p.x, p.g - .3, p.z).userData.stands = true;
    }
    box(9, 8, 9, 0xd5d0c4, top.x, y0 - 2, top.z); // the start tower's cabin
    box(1.6, y0 - 2 - top.g + .3, 1.6, steel, top.x, top.g - .3, top.z).userData.stands = true;
  });
});
