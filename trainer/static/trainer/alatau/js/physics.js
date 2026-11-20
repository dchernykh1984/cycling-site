'use strict';
/* ---------------- Физика ---------------- */
// The ride's physics in one place: numbers and formulas only, nothing that reads the page or draws.
const TRAINERS = { // мощность по скорости колеса на станке, км/ч → Вт
  fluid: v => 3.0 * v + 0.0045 * v * v * v,
  mag: v => 7.5 * v + 0.0012 * v * v * v,
  rollers: v => 4.0 * v + 0.0006 * v * v * v
};
const PHYS = { g: 9.81, CdA: .32, Crr: .005, bike: 8.5 };
// The air's density at a height in metres above the sea, kg/m3, by the International Standard Atmosphere (ISO 2533):
// 1.225 at the sea at 15 C, the air cooling 6.5 C a kilometre up to 11 km
function airDensity(h) { return 1.225 * Math.pow(1 - .0065 * clamp(h || 0, -500, 11000) / 288.15, 4.25588); }
// Drafting: the share of a rider's air drag saved in another rider's wake, by the gap between their wheels and the
// sideways offset between them, in metres. From on-site measurements of riders pedalling at 45 km/h (Spoelstra,
// Mahalingesh, Sciacchitano 2020, "Drafting Effect in Cycling: On-Site Aerodynamic Investigation by the 'Ring of
// Fire'", Proceedings 49(1):113, doi:10.3390/proceedings2020049113): 45 % saved in line 0.7 m back, 1.3 points more
// for each 10 cm closer, 3.9 points less for each 10 cm aside. They rode 0.35-0.85 m back and up to 0.2 m aside.
// Further out the same slopes are assumed, which no open measurement checks: the saving is gone 4.2 m back, or
// about 1.2 m aside.
const DRAFT = { share: .45, at: .7, back: .13, side: .39 };
function draftShare(gap, side) { return gap < 0 ? 0 : clamp(DRAFT.share - DRAFT.back * (gap - DRAFT.at) - DRAFT.side * Math.abs(side), 0, 1); }
// a rider's step: r.rho is the air they are in, r.draft the share of their drag a wake ahead takes
function stepRider(r, P, grade, dt) {
  const m = r.mass + (r.bike || PHYS.bike), th = Math.atan(grade);
  const v = Math.max(r.v, .5);
  const F = P / v - .5 * r.rho * r.CdA * (1 - r.draft) * r.v * r.v - (r.Crr || PHYS.Crr) * m * PHYS.g * Math.cos(th) - m * PHYS.g * Math.sin(th);
  r.v = Math.max(0, r.v + F / (m * 1.04) * dt);
  if (r.v > 30) r.v = 30;
  return r.v * dt;
}
// riding by the gear rather than the power: the speed eases towards the one the gear and cadence give
function directStep(r, kmh, dt) { const t = (kmh || 0) / 3.6; r.v += (t - r.v) * (1 - Math.exp(-dt * 3)); if (t === 0 && r.v < .05) r.v = 0; return r.v * dt; }
// Аэродинамика по росту и весу: лобовая площадь гонщика с велосипедом (формула Бассетта и соавт., 1999)
// A = 0,0293 · рост(м)^0,725 · вес(кг)^0,425 + 0,0604; CdA = 0,88 · A (посадка с руками на тормозных ручках)
function riderAero(hcm, kg) { const A = 0.0293 * Math.pow((hcm || 178) / 100, .725) * Math.pow(kg || 75, .425) + .0604; return { A, CdA: A * .88 }; }
// the bots: power by level (W/kg), surges, and each one's way of racing
const LEVELS = { easy: [1.8, 2.4], mid: [2.5, 3.2], hard: [3.3, 4.2] };
function styleMult(b, grade, toFinish, t) {
  switch (b.ch.style) {
    case 'climber': return grade > .03 ? 1.13 : .96;
    case 'sprinter': return toFinish < 450 ? 1.32 : .97;
    case 'rouleur': return Math.abs(grade) < .02 ? 1.06 : .97;
    case 'attacker': return ((t + b.seed * 9) % 90) < 16 ? 1.27 : .95;
    default: return 1;
  }
}
function botPower(b, grade, toFinish, t) {
  const surge = 1 + .08 * Math.sin(t * .21 + b.seed) + .05 * Math.sin(t * .9 + b.seed * 2) + (grade > .03 ? .08 : 0);
  return b.finishT != null ? 70 : b.wkg * b.mass * surge * styleMult(b, grade, toFinish, t);
}
function botCadence(b, grade, t) {
  return b.v > .5 ? clamp((b.finishT != null ? 62 : (b.ch.style === 'sprinter' ? 94 : b.ch.style === 'climber' ? 86 : 90)) + Math.sin(t * .37 + b.seed) * 4 - Math.max(0, grade) * 120, 58, 115) : 0;
}
// a smart trainer (FTMS) is set to the route's grade scaled by the difficulty, with no wind, and to the
// rider's own drag as the ride counts it: rolling resistance Crr and wind resistance Cw = CdA·ρ in kg/m
// (as ANT+ FE-C defines it: frontal area × drag coefficient × air density; the air drag is ½·Cw·v²), less
// the share a wake ahead takes
function trainerGrade(gradePct, difficulty) { return Math.round(gradePct * difficulty / 100 * 10) / 10; }
function trainerDrag(r) { return { crr: r.Crr || PHYS.Crr, cw: r.CdA * (1 - r.draft) * r.rho }; }
