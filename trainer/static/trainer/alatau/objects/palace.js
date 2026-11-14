'use strict';
/* A dark block under a wide white roof on columns. */
addObject('palace', (G, lm, T, { box }) => {
  box(80, 16, 54, 0x34404b, 0, -1);
  box(98, 3, 70, 0xdcdad2, 0, 15);
  for (let i = 0; i < 12; i++) { box(1.6, 15, 1.6, 0xeceae4, -38 + i * 6.9, -1, 27.5); box(1.6, 15, 1.6, 0xeceae4, -38 + i * 6.9, -1, -27.5); }
  box(26, 2, 14, 0x9aa3a8, 0, -1, 40);
});
