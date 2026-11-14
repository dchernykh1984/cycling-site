'use strict';
/* A white column on a square, a golden winged figure on top. */
addObject('monument', (G, lm, T, { lam, box, cyl }) => {
  box(90, .4, 90, 0xc9c3b6, 0, -.2);
  box(14, 2, 14, 0xb7b0a2, 0, 0); box(10, 2, 10, 0xc6bfb0, 0, 2);
  cyl(1.4, 2.3, 26, 0xf2efe7, 0, 4, 0, 12);
  cyl(1.6, 1.6, 1.4, 0xd9a92e, 0, 30, 0, 12); cyl(.7, .9, 3.2, 0xd9a92e, 0, 31.4, 0, 8);
  const head = new THREE.Mesh(new THREE.SphereGeometry(.75, 10, 8), lam(0xd9a92e)); head.position.y = 35.2; G.add(head);
  [-1, 1].forEach(s => { const w = box(3.6, .4, 1.4, 0xd9a92e, s * 2.2, 33, 0); w.rotation.z = s * .5; });
});
