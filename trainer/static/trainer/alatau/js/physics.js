'use strict';
/* ---------------- Физика ---------------- */
const TRAINERS = { // мощность по скорости колеса на станке, км/ч → Вт
  fluid: v => 3.0 * v + 0.0045 * v * v * v,
  mag: v => 7.5 * v + 0.0012 * v * v * v,
  rollers: v => 4.0 * v + 0.0006 * v * v * v
};
const COGS = [11, 12, 13, 14, 15, 17, 19, 21, 24, 28];
const PHYS = { g: 9.81, rho: 1.08, CdA: .32, Crr: .005, bike: 8.5 };
function stepRider(r, P, grade, dt) {
  const m = r.mass + (r.bike || PHYS.bike), th = Math.atan(grade);
  const v = Math.max(r.v, .5);
  const F = P / v - .5 * PHYS.rho * r.CdA * r.v * r.v - (r.Crr || PHYS.Crr) * m * PHYS.g * Math.cos(th) - m * PHYS.g * Math.sin(th);
  r.v = Math.max(0, r.v + F / (m * 1.04) * dt);
  if (r.v > 30) r.v = 30;
  return r.v * dt;
}
