'use strict';
/* A Ferris wheel on two A-frame legs, its cabins hanging round the rim; lm.h its height (30 m unless given), lm.rot
   the way its face turns. */
addObject('wheel', (G, lm, T, { lam, box, cyl }) => {
  const H = lm.h || 30, R = H / 2 - 1.2, hub = H - R - 1.2, white = lam(0xf1f1ec), rim = Math.max(.22, H / 130);
  for (const k of [-.9, .9]) {
    const ring = new THREE.Mesh(new THREE.TorusGeometry(R, rim, 6, 72), white); ring.position.set(0, hub, k); G.add(ring);
  }
  const spokes = 24, cabins = Math.round(H * .6), colours = [0xd8443a, 0x2f78c8, 0xf0b62e, 0x3a9a55];
  for (let i = 0; i < spokes; i++) {
    const a = i / spokes * Math.PI * 2, s = new THREE.Mesh(new THREE.CylinderGeometry(rim * .45, rim * .45, R, 4), white);
    s.position.set(Math.cos(a) * R / 2, hub + Math.sin(a) * R / 2, 0); s.rotation.z = a - Math.PI / 2; G.add(s);
  }
  for (let i = 0; i < cabins; i++) {
    const a = i / cabins * Math.PI * 2, x = Math.cos(a) * R, y = hub + Math.sin(a) * R, c = Math.max(1.4, H / 22);
    box(c, c * 1.15, c, colours[i % colours.length], x, y - c * 1.3, 0);
  }
  // the legs: an A-frame either side of the wheel, from the ground to the hub
  for (const k of [-1, 1]) for (const s of [-1, 1]) {
    const foot = R * .62, leg = new THREE.Mesh(new THREE.CylinderGeometry(rim * 1.4, rim * 2.2, Math.hypot(foot, hub), 6), white);
    leg.position.set(s * foot / 2, hub / 2, k * 2.2); leg.rotation.z = -s * Math.atan2(foot, hub); G.add(leg);
  }
  cyl(rim * 2.5, rim * 2.5, 5, 0xbfc3c6, 0, hub, -2.5, 8).rotation.x = Math.PI / 2;
  box(R * 1.6, .6, 6, 0xb9b6ae, 0, 0, 0);
});
