'use strict';
/* A theatre with a portico of columns. */
addObject('opera', (G, lm, T, { box, cyl }) => {
  const cream = 0xf0e2c0;
  box(64, 17, 52, cream, 0, -1); box(36, 27, 34, cream, 0, -1); box(40, 1.6, 38, 0xd9cfb6, 0, 26);
  for (let i = 0; i < 8; i++) cyl(1.1, 1.3, 13, 0xfbf8f0, -14 + i * 4, 0, 29, 10);
  box(36, 3.5, 6, 0xfbf8f0, 0, 13, 29); box(32, 2.5, 5, 0xfbf8f0, 0, 16.5, 29).scale.x = .9;
  G.rotation.y = -Math.PI / 2;
});
