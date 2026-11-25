'use strict';
/* A slab block, the sight's h tall, under a golden crown. */
addObject('hotel', (G, lm, T, { lam, sink }) => {
  const m = new THREE.Mesh(new THREE.BoxGeometry(22, lm.h + sink, 40), buildingMat); m.position.y = (lm.h + sink) / 2 - 2 - sink; G.add(m);
  const crown = new THREE.Mesh(new THREE.CylinderGeometry(3, 12, 18, 4), lam(0xd4a648)); crown.position.y = lm.h + 7; G.add(crown);
});
