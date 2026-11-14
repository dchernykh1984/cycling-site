'use strict';
/* An earth dam across a gorge, with a stair up its face. */
addObject('dam', (G, lm, T, { lam, box }) => {
  // земляная плотина поперёк ущелья
  const g = new THREE.BoxGeometry(1, 1, 1), p = g.attributes.position;
  for (let i = 0; i < p.count; i++) { const top = p.getY(i) > 0; p.setXYZ(i, p.getX(i) * (top ? 720 : 140), top ? 150 : -20, p.getZ(i) * (top ? 36 : 380)); }
  g.computeVertexNormals(); const m = new THREE.Mesh(g, lam(0x9a9566)); G.add(m);
  box(1440, 4, 40, 0xb9b6ae, 0, 148);
  const stairs = new THREE.Mesh(new THREE.BoxGeometry(22, 2, 250), lam(0xe6e3dc)); stairs.position.set(0, 66, -104); stairs.rotation.x = -Math.atan2(170, 172); G.add(stairs);
  [-1, 1].forEach(k => { const t = new THREE.Mesh(new THREE.BoxGeometry(6, 1.5, 250), lam(0x5f6b3c)); t.position.set(k * 80, 66, -104); t.rotation.x = stairs.rotation.x; G.add(t); });
  const o = sampleAt(T, T.L, {}); G.rotation.y = Math.atan2(lm.x - o.x, lm.z - o.z);
});
