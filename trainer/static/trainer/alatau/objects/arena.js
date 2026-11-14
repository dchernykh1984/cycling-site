'use strict';
/* A round sports hall under a low dome. */
addObject('arena', (G, lm, T, { lam, cyl }) => {
  cyl(38, 38, 16, 0xd8d4c8, 0, -1, 0, 32); cyl(38.6, 38.6, 4, 0x3a4550, 0, 9, 0, 32);
  const d = new THREE.Mesh(new THREE.SphereGeometry(38, 32, 10, 0, Math.PI * 2, 0, Math.PI / 2), lam(0xbfc4c8)); d.scale.y = .22; d.position.y = 15; G.add(d);
});
