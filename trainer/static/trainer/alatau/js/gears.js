'use strict';
/* ---------------- Велосипед, передачи и план по каденсу ---------------- */
// Нумерация как принято у велосипедистов: спереди 1 — самая маленькая звезда, сзади 1 — самая большая (самая лёгкая передача).
const FRONTS = { '50-34': [34, 50], '52-36': [36, 52], '53-39': [39, 53], '46-30': [30, 46], '48-35-26': [26, 35, 48], '1x40': [40], '1x44': [44] };
// задние звёзды от самой большой (1) к самой маленькой
const CASSETTES = {
  '10:11-25': [25, 23, 21, 19, 17, 15, 14, 13, 12, 11], '10:11-28': [28, 24, 21, 19, 17, 15, 14, 13, 12, 11],
  '10:12-25': [25, 23, 21, 19, 17, 16, 15, 14, 13, 12], '10:12-28': [28, 25, 23, 21, 19, 17, 15, 14, 13, 12],
  '10:11-32': [32, 28, 25, 23, 21, 19, 17, 15, 13, 11], '10:11-34': [34, 31, 28, 24, 21, 19, 17, 15, 13, 11], '10:11-36': [36, 32, 28, 24, 21, 19, 17, 15, 13, 11],
  '11-28': [28, 25, 23, 21, 19, 17, 15, 14, 13, 12, 11], '11-32': [32, 28, 25, 22, 20, 18, 16, 14, 13, 12, 11], '11-42': [42, 37, 32, 28, 24, 21, 19, 17, 15, 13, 11],
  '11-34': [34, 30, 27, 24, 21, 19, 17, 15, 14, 13, 12, 11]
};
const CASS_GROUPS = [[t('cass.n', { n: 10 }), ['10:11-25', '10:11-28', '10:12-25', '10:12-28', '10:11-32', '10:11-34', '10:11-36']], [t('cass.n', { n: 11 }), ['11-28', '11-32', '11-42']], [t('cass.n', { n: 12 }), ['11-34']]];
const cassName = k => k.replace('10:', '').replace('-', '–');
const FRONT_LABEL = { '50-34': '50/34 (' + t('front.compact') + ')', '52-36': '52/36', '53-39': '53/39', '46-30': '46/30 (' + t('front.gravel') + ')', '48-35-26': '48/35/26 (' + t('front.triple') + ')', '1x40': '1× 40', '1x44': '1× 44', custom: t('bike.custom') };
function parseTeeth(str, min, max) { const a = String(str || '').split(/[^0-9]+/).map(Number).filter(n => n >= min && n <= max); return a; }
const bikeF = () => settings.plan.front === 'custom' && (settings.plan.frontCustom || []).length ? settings.plan.frontCustom : (FRONTS[settings.plan.front] || FRONTS['50-34']);
const bikeR = () => settings.plan.cass === 'custom' && (settings.plan.cassCustom || []).length ? settings.plan.cassCustom : (CASSETTES[settings.plan.cass] || CASSETTES['10:11-28']);
const gearTeeth = (f, r) => [bikeF()[clamp(f, 1, bikeF().length) - 1], bikeR()[clamp(r, 1, bikeR().length) - 1]];
const gearLabel = (f, r) => f + '×' + r;
let gearF = 2, gearR = 6;
function defaultPlan() {
  return { front: '50-34', cass: '10:11-28', updated: 0, steps: [
    { f: 1, r: 1, cad: 80, min: 5 }, { f: 1, r: 2, cad: 80, min: 5 }, { f: 1, r: 3, cad: 85, min: 5 },
    { f: 1, r: 4, cad: 85, min: 5 }, { f: 2, r: 3, cad: 90, min: 3 }, { f: 1, r: 1, cad: 75, min: 5 }] };
}
if (!settings.plan || !Array.isArray(settings.plan.steps)) settings.plan = defaultPlan();
if (!settings.mode) settings.mode = 'race';
if (!CASSETTES[settings.plan.cass] && settings.plan.cass !== 'custom') settings.plan.cass = '10:11-28';
if (!settings.plan.updated && settings.plan.cass === '11-32') settings.plan.cass = '10:11-28';
let planSaveT = null;
function savePlan() {
  settings.plan.updated = Date.now(); store.set('settings', settings);
  if (Records.data) { Records.data.plan = settings.plan; clearTimeout(planSaveT); planSaveT = setTimeout(() => Records.save(), 1200); }
  renderPlanTotal();
}
function syncPlanFromRecords() {
  const rp = Records.data && Records.data.plan;
  if (rp && Array.isArray(rp.steps) && (rp.updated || 0) > (settings.plan.updated || 0)) { settings.plan = JSON.parse(JSON.stringify(rp)); store.set('settings', settings); renderPlanEditor(); }
}
const planTotalMin = () => settings.plan.steps.reduce((a, s) => a + (+s.min || 0), 0);
function renderPlanTotal() {
  const m = planTotalMin(); $('#plTotal').textContent = t('plan.total', { n: settings.plan.steps.length, t: fmtTime(m * 60) });
}
function opts(n, teeth, sel) { let h = ''; for (let i = 1; i <= n; i++) h += '<option value="' + i + '"' + (i === sel ? ' selected' : '') + '>' + i + ' (' + teeth[i - 1] + ')</option>'; return h; }
function renderPlanEditor() {
  const P = settings.plan, F = bikeF(), R = bikeR();
  document.querySelectorAll('#modeSeg button').forEach(b => b.setAttribute('aria-pressed', b.dataset.mode === settings.mode ? 'true' : 'false'));
  $('#planEd').classList.toggle('hidden', settings.mode !== 'plan');
  $('#raceOpts').classList.toggle('hidden', settings.mode !== 'race');
  $('#plFront').innerHTML = Object.keys(FRONTS).concat('custom').map(k => '<option value="' + k + '"' + (k === P.front ? ' selected' : '') + '>' + FRONT_LABEL[k] + '</option>').join('');
  $('#plCass').innerHTML = CASS_GROUPS.map(g => '<optgroup label="' + g[0] + '">' + g[1].map(k => '<option value="' + k + '"' + (k === P.cass ? ' selected' : '') + '>' + cassName(k) + '</option>').join('') + '</optgroup>').join('') + '<option value="custom"' + (P.cass === 'custom' ? ' selected' : '') + '>' + t('bike.custom') + '</option>';
  $('#plFrontCustomF').classList.toggle('hidden', P.front !== 'custom'); $('#plCassCustomF').classList.toggle('hidden', P.cass !== 'custom');
  if (document.activeElement !== $('#plFrontCustom')) $('#plFrontCustom').value = (P.frontCustom || []).slice().reverse().join('-');
  if (document.activeElement !== $('#plCassCustom')) $('#plCassCustom').value = (P.cassCustom || []).slice().reverse().join('-');
  $('#plBikeInfo').textContent = t('bike.info', { f: F.length, fl: F.slice().reverse().join('/'), r: R.length, rl: R[R.length - 1] + '–' + R[0] });
  P.steps.forEach(s => { s.f = clamp(s.f, 1, F.length); s.r = clamp(s.r, 1, R.length); });
  const s0 = P.steps[0] || { f: 1, r: 1 };
  $('#plStartF').innerHTML = opts(F.length, F, s0.f); $('#plStartR').innerHTML = opts(R.length, R, s0.r);
  const ol = $('#plSteps'); ol.innerHTML = '';
  P.steps.forEach((s, i) => {
    const li = document.createElement('li');
    li.innerHTML = '<span class="n">' + (i + 1) + '</span>' +
      '<span class="g"><select class="sf" aria-label="' + t('plan.stepFront', { n: i + 1 }) + '">' + opts(F.length, F, s.f) + '</select><span>×</span><select class="sr" aria-label="' + t('plan.stepRear', { n: i + 1 }) + '">' + opts(R.length, R, s.r) + '</select></span>' +
      '<label class="c"><input class="sc" type="number" min="40" max="140" step="5" inputmode="numeric" value="' + s.cad + '" aria-label="' + t('plan.stepCad', { n: i + 1 }) + '"><span>' + t('u.rpm') + '</span></label>' +
      '<label class="m"><input class="sm" type="number" min="0.5" max="60" step="0.5" inputmode="decimal" value="' + s.min + '" aria-label="' + t('plan.stepMin', { n: i + 1 }) + '"><span>' + t('u.min') + '</span></label>' +
      '<button class="x" type="button" aria-label="' + t('plan.stepDel', { n: i + 1 }) + '">×</button>';
    li.querySelector('.sf').onchange = e => { s.f = +e.target.value; savePlan(); if (i === 0) renderPlanEditor(); };
    li.querySelector('.sr').onchange = e => { s.r = +e.target.value; savePlan(); if (i === 0) renderPlanEditor(); };
    li.querySelector('.sc').onchange = e => { s.cad = clamp(Math.round(+e.target.value || 80), 40, 140); e.target.value = s.cad; savePlan(); };
    li.querySelector('.sm').onchange = e => { s.min = clamp(Math.round((+e.target.value || 1) * 2) / 2, .5, 60); e.target.value = s.min; savePlan(); };
    li.querySelector('.x').onclick = () => { if (P.steps.length > 1) { P.steps.splice(i, 1); savePlan(); renderPlanEditor(); } };
    ol.appendChild(li);
  });
  renderPlanTotal(); if (phase === 'menu') renderStartSum();
}
// смена стартовой передачи сдвигает весь план на ту же разницу
function shiftPlan(df, dr) {
  const F = bikeF(), R = bikeR();
  settings.plan.steps.forEach(s => { s.f = clamp(s.f + df, 1, F.length); s.r = clamp(s.r + dr, 1, R.length); });
  savePlan(); renderPlanEditor();
}
