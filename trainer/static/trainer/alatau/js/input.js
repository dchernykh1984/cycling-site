'use strict';
/* ---------------- Ввод мощности ---------------- */
function readInput() {
  const mode = Sensors.mode(), circ = settings.circ / 1000, curve = TRAINERS[settings.trainer] || TRAINERS.fluid;
  let P = 0, cad = Sensors.crank(), wheelKmh = 0;
  if (mode === 'power') { P = Sensors.power(); }
  else if (mode === 'speed') { wheelKmh = Sensors.wheel() * circ * 60 / 1000; P = curve(wheelKmh); }
  else if (mode === 'cadence') { const gt = gearTeeth(gearF, gearR), ratio = gt[0] / gt[1]; wheelKmh = cad * ratio * circ * 60 / 1000; P = curve(wheelKmh); }
  else { P = demoP; cad = P > 0 ? (Work.active && Work.idx >= 0 ? Work.cur().cad + Math.sin(clockT * .7) * 3 : clamp(70 + P / 12, 70, 100)) : 0; }
  // скорость по передаче: каденс × (передняя звезда / задняя) × окружность колеса
  let direct = false;
  if (mode === 'demo' && Work.active && Work.idx >= 0) { const gt = gearTeeth(gearF, gearR); wheelKmh = cad * gt[0] / gt[1] * circ * 60 / 1000; P = curve(wheelKmh); direct = true; }
  if (mode === 'cadence' && settings.cadSpeed !== 'physics') direct = true;
  return { P, cad, mode, wheelKmh, direct };
}
function updateModeUI() {
  const mode = Sensors.mode(), inRace = phase === 'race' || phase === 'countdown';
  $('#demo').classList.toggle('hidden', !(inRace && mode === 'demo'));
  $('#gear').classList.toggle('hidden', !(inRace && mode === 'cadence'));
  $('#uPower').textContent = mode === 'demo' ? t('u.wDemo') : mode === 'power' ? t('u.w') : t('u.wEst');
  const gt = gearTeeth(gearF, gearR); $('#gearV').textContent = gearLabel(gearF, gearR) + ' · ' + gt[0] + '×' + gt[1];
  if (phase === 'menu') renderStartSum();
}
const ZONE_BG = ['', 'rgba(110,125,140,.82)', 'rgba(61,123,182,.85)', 'rgba(76,124,85,.86)', 'rgba(214,140,40,.9)', 'rgba(195,50,59,.92)'];
function hrZone(hr) { const p = hr / settings.hrmax; return p < .6 ? 1 : p < .7 ? 2 : p < .8 ? 3 : p < .9 ? 4 : 5; }
function fmtPct(p) { return numF(Math.round(p * 10) / 10, 1).replace(/[.,]0$/, '') + '%'; }
