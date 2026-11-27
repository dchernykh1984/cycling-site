'use strict';
/* A lake as OpenStreetMap outlines it (lm.outline, [[latitude, longitude], ...]): its water lm.c (Big Almaty Lake's
   turquoise unless given) flat at the lowest of the land round its shore, and the land inside the shore laid under
   it (a pad) -- the ground's cells, tens of metres across, would show through it where SRTM's lake is not flat. */
const lakeLevel = (lm, T) => {
  if (lm.level != null) return lm.level;
  lm.ring = lm.outline.map(p => { const q = proj(p[0], p[1], T.origin); return [q.x, q.z]; });
  lm.level = Math.min(...lm.ring.map(([x, z]) => terrainH(T, x, z))) + .05;
  return lm.level;
};
addObject('lake', (G, lm, T) => {
  G.userData.spread = true; const y = lakeLevel(lm, T); G.position.set(lm.x, y, lm.z);
  const shape = new THREE.Shape(lm.ring.map(([x, z]) => new THREE.Vector2(x - lm.x, -(z - lm.z))));
  const g = new THREE.ShapeGeometry(shape); g.rotateX(-Math.PI / 2);
  G.add(new THREE.Mesh(g, new THREE.MeshLambertMaterial({ color: lm.c || 0x35a3ab })));
}, (lm, T) => ({ ring: (lakeLevel(lm, T), lm.ring), y: lm.level - .6, margin: 1 }));
