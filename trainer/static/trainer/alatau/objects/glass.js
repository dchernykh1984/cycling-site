'use strict';
/* A glass tower, the sight's h tall, under a tilted top. */
addObject('glass', (G, lm, T, { box }) => {
  box(34, lm.h, 26, 0x6f8aa2, 0, -2); G.rotation.y = .3; box(30, 6, 22, 0x8aa2b8, 0, lm.h - 2).rotation.z = .12;
});
