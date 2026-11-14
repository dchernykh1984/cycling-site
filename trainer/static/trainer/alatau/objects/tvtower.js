'use strict';
/* A TV tower on its hill: a lattice mast with three decks. */
addObject('tvtower', (G, lm, T, { lam, cyl }) => {
  const hill = new THREE.Mesh(new THREE.ConeGeometry(700, 230, 24, 1), lam(0x667a4c)); hill.position.y = -175; G.add(hill);
  const t = new THREE.Mesh(new THREE.CylinderGeometry(1.6, 13, 372, 6, 1, true), new THREE.MeshLambertMaterial({ color: 0xc9ccd0, wireframe: true })); t.position.y = 126; G.add(t);
  [120, 210, 300].forEach(h => cyl(8 - h / 60, 8 - h / 60, 4, 0xe8e8e8, 0, h - 60, 0, 12));
});
