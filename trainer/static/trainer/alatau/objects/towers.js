'use strict';
/* Three oval towers on one base. */
addObject('towers', (G, lm, T, { box, cyl }) => {
  box(80, 10, 50, 0x8a99a6, 0, -1);
  [[-20, 0, 14, 128], [8, -8, 12, 104], [26, 10, 10, 82]].forEach(t => { const m = cyl(t[2], t[2], t[3], 0x5f86a8, t[0], 0, t[1], 24); m.scale.x = 1.5; cyl(t[2] * .9, t[2], 4, 0x9fb6c8, t[0], t[3], t[1], 24).scale.x = 1.5; });
});
