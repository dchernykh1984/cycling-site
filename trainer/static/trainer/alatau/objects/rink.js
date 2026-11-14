'use strict';
/* A skating rink between two stands, on the floor of a valley. */
addObject('rink', (G, lm, T, { box }) => {
  // каток лежит на дне долины, длинной стороной вдоль ущелья
  const o = sampleAt(T, T.L, {}); G.position.y = nearest(T, lm.x, lm.z).y - 1; G.rotation.y = Math.atan2(lm.x - o.x, lm.z - o.z);
  box(130, 6, 190, 0x9aa0a6, 0, -5); box(100, .6, 160, 0xe4f1fb, 0, 1);
  [-1, 1].forEach(k => { const st = new THREE.Mesh(new THREE.BoxGeometry(16, 20, 190), buildingMat); st.position.set(k * 74, 9, 0); G.add(st); });
});
