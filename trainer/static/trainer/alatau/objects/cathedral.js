'use strict';
/* A wooden cathedral with onion domes and a bell tower. */
addObject('cathedral', (G, lm, T, { box, cyl, onion }) => {
  // деревянный собор: пастельные стены, красные крыши, луковичные главы
  const wall = 0xf3e2a6, roof = 0xc96a6a, gold = 0xe2b23c;
  box(22, 16, 44, wall, 0, -1); box(42, 14, 18, wall, 0, -1);
  box(24, 1.6, 46, roof, 0, 15); box(44, 1.6, 20, roof, 0, 13);
  cyl(7, 7, 12, wall, 0, 15, 0, 8); cyl(7.6, 7.6, 1.2, roof, 0, 26.5, 0, 8); onion(7, gold, 0, 27.5, 0, 6);
  [[-9, -9], [9, -9], [-9, 9], [9, 9]].forEach(p => { cyl(2.6, 2.6, 7, wall, p[0], 15, p[1], 8); onion(2.8, roof, p[0], 22, p[1], 3); });
  box(11, 28, 11, wall, 0, -1, -27); box(12, 1.4, 12, roof, 0, 26.5, -27); box(8, 9, 8, wall, 0, 27.5, -27); onion(4, gold, 0, 36.5, -27, 7);
  G.rotation.y = Math.PI / 2;
});
