'use strict';
/* ---------------- Ввод мощности ---------------- */
function readInput() {
  // the power a wheel or cadence sensor alone gives on the rider's trainer: a smart trainer sends its own, and ridden
  // by such a sensor alone it counts as a fluid one
  const mode = Sensors.mode(), circ = settings.circ / 1000, curve = TRAINERS[settings.trainer] || TRAINERS.fluid;
  let P = 0, cad = Sensors.crank(), wheelKmh = 0;
  if (mode === 'power') { P = Sensors.power(); }
  else if (mode === 'speed') { wheelKmh = Sensors.wheel() * circ * 60 / 1000; P = curve(wheelKmh); }
  else if (mode === 'cadence') { const gt = gearTeeth(gearF, gearR), ratio = gt[0] / gt[1]; wheelKmh = cad * ratio * circ * 60 / 1000; P = curve(wheelKmh); }
  else {
    // the demo rides a plan for the rider: a workout's power, the step's cadence
    const s = Work.active && Work.idx >= 0 ? Work.cur() : null;
    P = s && s.w != null ? Work.target() : demoP; cad = P > 0 ? (s && s.cad ? s.cad + Math.sin(clockT * .7) * 3 : clamp(70 + P / 12, 70, 100)) : 0;
  }
  // скорость по передаче: каденс × (передняя звезда / задняя) × окружность колеса.
  // A step of the own plan by gears rides at its gear's speed; otherwise a cadence sensor alone rides by the physics,
  // unless the rider chose the gear's speed
  let direct = false; const byGear = Work.active && Work.idx >= 0 && Work.cur().f != null;
  if (mode === 'demo' && byGear) { const gt = gearTeeth(gearF, gearR); wheelKmh = cad * gt[0] / gt[1] * circ * 60 / 1000; P = curve(wheelKmh); direct = true; }
  if (mode === 'cadence' && (byGear || settings.cadSpeed === 'direct')) direct = true;
  return { P, cad, mode, wheelKmh, direct, hr: Sensors.hr(), rr: Sensors.takeRR() }; // rr: the strap's RR intervals since the last frame
}
// The demo's power from its slider's place, 0..1000, and back: up to 5 kW on a curve, finer where most ride -- a step
// of the slider under a watt up to 150 W, 25 W at the top -- in 5 W
const DEMO_MAX_W = 5000, DEMO_CURVE = 5;
function demoWatts(pos) { return Math.round(DEMO_MAX_W * Math.expm1(DEMO_CURVE * pos / 1000) / Math.expm1(DEMO_CURVE) / 5) * 5; }
function demoPos(w) { return Math.round(1000 * Math.log1p(w / DEMO_MAX_W * Math.expm1(DEMO_CURVE)) / DEMO_CURVE); }
// the slider at a place, its power ridden, shown, and said to a screen reader in watts rather than the place
function setDemo(pos) {
  const p = clamp(Math.round(pos), 0, 1000), el = $('#demoP'), said = demoWatts(p) + ' ' + t('u.w');
  demoP = demoWatts(p); el.value = p; el.setAttribute('aria-valuetext', said); $('#demoV').textContent = said;
}
function updateModeUI() {
  const mode = Sensors.mode(), inRace = phase === 'race' || phase === 'countdown';
  $('#demo').classList.toggle('hidden', !(inRace && mode === 'demo'));
  $('#gear').classList.toggle('hidden', !(inRace && mode === 'cadence'));
  $('#uPower').textContent = mode === 'demo' ? t('u.wDemo') : mode === 'power' ? t('u.w') : t('u.wEst');
  const gt = gearTeeth(gearF, gearR); $('#gearV').textContent = gearLabel(gearF, gearR) + ' · ' + gt[0] + '×' + gt[1];
  // ERG on or off, while a workout with power steps rides on a trainer that holds a power
  const erg = $('#btnErg'); erg.classList.toggle('hidden', !(inRace && rideMode === 'plan' && Work.active && Work.steps.some(s => s.w != null) && Trainer.canErg()));
  erg.setAttribute('aria-pressed', settings.erg !== false ? 'true' : 'false');
  if (phase === 'menu') renderStartSum();
}
const ZONE_BG = ['', 'rgba(110,125,140,.82)', 'rgba(61,123,182,.85)', 'rgba(76,124,85,.86)', 'rgba(214,140,40,.9)', 'rgba(195,50,59,.92)'];
function hrZone(hr) { const p = hr / settings.hrmax; return p < .6 ? 1 : p < .7 ? 2 : p < .8 ? 3 : p < .9 ? 4 : 5; }
function fmtPct(p) { return numF(Math.round(p * 10) / 10, 1).replace(/[.,]0$/, '') + '%'; }
