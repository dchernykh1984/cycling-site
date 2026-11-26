'use strict';
/* A TV tower: a lattice mast with three decks, lm.h tall (372 m unless given), on its hill unless lm.hill is false. */
addObject('tvtower', (G, lm, T, { lam, cyl, sink }) => {
  // on its hill the mast stands in the hill; on the land its foot goes as deep as the land under it asks
  const H = lm.h || 372, k = H / 372, base = lm.hill === false ? 0 : -60, deep = lm.hill === false ? sink : 0;
  if (lm.hill !== false) { const hill = new THREE.Mesh(new THREE.ConeGeometry(700, 230, 24, 1), lam(0x667a4c)); hill.position.y = -175; G.add(hill); }
  const t = new THREE.Mesh(new THREE.CylinderGeometry(1.6 * k, 13 * k, H + deep, 6, 1, true), new THREE.MeshLambertMaterial({ color: 0xc9ccd0, wireframe: true })); t.position.y = base - deep + (H + deep) / 2; G.add(t);
  [120, 210, 300].forEach(h => cyl((8 - h / 60) * k, (8 - h / 60) * k, 4 * k, 0xe8e8e8, 0, base + h * k, 0, 12));
});
