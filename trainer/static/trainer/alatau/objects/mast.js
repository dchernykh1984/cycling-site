'use strict';
/* A mobile phone mast: a three-sided lattice tower lm.h tall (30 m unless given), narrowing to its top -- drawn as
   its lines, which stay a pixel wide however far it stands, as the TV tower's do -- its three antennas and a dish
   there over a platform, and at its foot a fenced compound with its equipment cabinets. */
const MAST_FOOT_R = 1.45, MAST_TOP_R = .45, MAST_COMPOUND = 9;
addObject('mast', (G, lm, T, { lam, box, cyl, sink }) => {
  const H = lm.h || 30, steel = new THREE.MeshLambertMaterial({ color: 0x5f666c, wireframe: true }); // dark against the sky
  const tower = new THREE.Mesh(new THREE.CylinderGeometry(MAST_TOP_R, MAST_FOOT_R, H + sink, 3, Math.round(H / 2), true), steel);
  tower.position.y = (H - sink) / 2; G.add(tower);
  // the antennas round its top, each turned out from the tower; the platform under them; a dish below
  for (let k = 0; k < 3; k++) {
    const a = k * 2 * Math.PI / 3, panel = box(.35, 2.2, .14, 0xeeeeea, Math.sin(a) * (MAST_TOP_R + .5), H - 2.6, Math.cos(a) * (MAST_TOP_R + .5));
    panel.rotation.y = a;
  }
  cyl(MAST_TOP_R + .8, MAST_TOP_R + .8, .15, 0x9aa0a6, 0, H - 3, 0, 6);
  cyl(.55, .55, .25, 0xeeeeea, MAST_TOP_R + .3, H - 6.5, 0, 14).rotation.z = Math.PI / 2;
  // the compound: two cabinets and a wire fence round it
  const white = lam(0xe6e6e0);
  box(2.4, 2.3, 1.3, white, -2.6, 0, -2.4); box(2.4, 2.3, 1.3, white, -2.6, 0, -.6);
  const fence = new THREE.MeshLambertMaterial({ color: 0x8d9296, wireframe: true }), half = MAST_COMPOUND / 2;
  [[0, -half, 0], [0, half, 0], [-half, 0, Math.PI / 2], [half, 0, Math.PI / 2]].forEach(([x, z, turn]) => {
    const side = new THREE.Mesh(new THREE.PlaneGeometry(MAST_COMPOUND, 2, 9, 2), fence);
    side.position.set(x, 1, z); side.rotation.y = turn; G.add(side);
  });
});
