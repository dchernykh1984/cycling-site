'use strict';
/* A checkpoint over the road, an eco-post's or a toll's: a canopy across the route where it passes the sight's
   place, lm.w metres along the road (12 unless given) and TOLL_ROOF_M over it, on pillars beyond its edges; a booth
   each side and its barrier arm raised; the name (lm.sign) on the canopy's front over the road both ways. */
const TOLL_ROOF_M = 5.6, TOLL_SIDE_M = 4;
addObject('tollgate', (G, lm, T, { lam, box, cyl }) => {
  const n = routeNearest(T, lm.x, lm.z), o = sampleAt(T, n.s, {}), W = T.route.width, along = lm.w || 12;
  // stand it on the road: the group at the road's middle and height, turned along it
  G.position.set(o.x, o.y, o.z); G.rotation.y = Math.atan2(o.tx, o.tz);
  const span = W + 2 * TOLL_SIDE_M, roof = lam(lm.c || 0x7d8a96), white = lam(0xefeee9), red = lam(0xc3323b);
  box(span + 1, .8, along, roof, 0, TOLL_ROOF_M, 0);
  [-1, 1].forEach(k => {
    [-along / 2 + .6, along / 2 - .6].forEach(z => cyl(.3, .3, TOLL_ROOF_M, white, k * (span / 2), 0, z, 10));
    // a booth on each side, beyond the road's edge
    box(2.2, 2.6, 3, white, k * (W / 2 + 2.2), 0, 0); box(2.4, .25, 3.2, roof, k * (W / 2 + 2.2), 2.6, 0);
    // the barrier arm, raised, at the booth's road side
    const arm = box(.12, W / 2 + .5, .12, red, k * (W / 2 + 1), 1.1, -1.6); arm.rotation.z = -k * .12;
  });
  // the name on the canopy's front, over the road, to the riders coming each way
  const tex = canvasTex(1024, 128, (c, w, h) => {
    c.fillStyle = '#1d4f3a'; c.fillRect(0, 0, w, h); c.fillStyle = '#ffffff'; c.textAlign = 'center'; c.textBaseline = 'middle';
    let size = 76; c.font = '700 ' + size + 'px Golos Text, sans-serif';
    while (c.measureText(lm.sign || '').width > w * .92 && size > 12) { size *= .92; c.font = '700 ' + size + 'px Golos Text, sans-serif'; }
    c.fillText(lm.sign || '', w / 2, h / 2 + 3);
  });
  const face = new THREE.MeshBasicMaterial({ map: tex }), green = lam(0x1d4f3a);
  [-1, 1].forEach(k => {
    const board = new THREE.Mesh(new THREE.BoxGeometry(W + 2, 1.1, .2), [green, green, green, green, face, green]);
    board.position.set(0, TOLL_ROOF_M + .4, k * (along / 2 + .15)); if (k < 0) board.rotation.y = Math.PI; G.add(board);
  });
});
