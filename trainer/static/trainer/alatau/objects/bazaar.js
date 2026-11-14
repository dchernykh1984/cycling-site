'use strict';
/* A market hall under a green vaulted roof. */
addObject('bazaar', (G, lm, T, { lam, box }) => {
  box(110, 10, 55, 0xd8c9a8, 0, -1);
  const r = new THREE.Mesh(new THREE.CylinderGeometry(27.5, 27.5, 110, 20, 1, false, 0, Math.PI), lam(0x3f8a5a)); r.rotation.z = Math.PI / 2; r.rotation.y = Math.PI / 2; r.scale.set(1, 1, .45); r.position.y = 9; G.add(r);
});
