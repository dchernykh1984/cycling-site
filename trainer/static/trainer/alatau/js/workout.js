'use strict';
/* ---- план во время заезда: подсказки и итоги (сам план выполняет заезд, js/ride.js) ---- */
let planListIdx = -2; // the step the list on the left was last drawn for
// a step of a workout by its power: watts, a ramp's two ends, or a free ride
const stepPower = s => s.w == null ? t('plan.freeStep') : (s.w2 != null && s.w2 !== s.w ? s.w + '–' + s.w2 : s.w) + ' ' + t('u.w');
// a step in a few words: its gear or its power, and the cadence it asks for
const stepWhat = s => (s.f != null ? gearLabel(s.f, s.r) : stepPower(s)) + (s.cad ? ', ' + s.cad + ' ' + t('u.rpm') : '');
// how near a figure is to its target: within near, within far, or off
const onTarget = (v, aim, near, far) => { const d = Math.abs(v - aim); return d <= near ? 'act-ok' : d <= far ? 'act-near' : 'act-off'; };
// the share of the time with a target that was spent on it, in per cent
const zonePct = ss => { const aimed = ss.reduce((a, x) => a + x.aimed, 0); return aimed ? Math.round(ss.reduce((a, x) => a + x.zone, 0) / aimed * 100) : 0; };
// whether a plan sets any target at all: a workout by heart rate comes without power, and has no time on target to tell
const aimsAt = steps => steps.some(s => s.w != null || s.cad);
function updatePlanHUD(cad, P) {
  if (!Work.active) return;
  // during the countdown the first step, as Work.cur() gives it: the target and the list are there from the start
  const i = Math.max(Work.idx, 0), s = Work.steps[i], nx = Work.steps[i + 1], left = Work.ends[i] - Work.t, dur = s.min * 60, n = Work.steps.length, w = Work.target();
  const rest = t('plan.leftLast', { t: fmtTime(Math.ceil(left)) });
  // the step's target beside the power: a gear and its cadence, or the watts (and the cadence, if asked)
  if (s.f != null) {
    const [ft, rt] = gearTeeth(s.f, s.r);
    $('#tTitle').textContent = t('plan.holdOn', { g: gearLabel(s.f, s.r), teeth: ft + '×' + rt });
    $('#tVal').textContent = s.cad; $('#tUnit').textContent = t('u.rpm');
    $('#tSub').textContent = nx ? t('plan.leftNext', { t: fmtTime(Math.ceil(left)), c: nx.cad }) : rest;
  } else {
    const how = w == null ? t('plan.freeHint') : s.w2 != null && s.w2 !== s.w ? t('plan.ramp', { w: s.w2 }) : Trainer.held != null ? t('plan.ergHolds') : t('plan.holdPower');
    $('#tTitle').textContent = how + (s.cad ? ', ' + s.cad + ' ' + t('u.rpm') : '');
    $('#tVal').textContent = w != null ? w : s.cad || '—'; $('#tUnit').textContent = w != null ? t('u.w') : s.cad ? t('u.rpm') : '';
    $('#tSub').textContent = nx ? t('plan.leftThen', { t: fmtTime(Math.ceil(left)), what: stepWhat(nx) }) : rest;
  }
  $('#tProg').style.width = clamp((dur - left) / dur * 100, 0, 100).toFixed(1) + '%';
  $('#vPower').className = w != null ? onTarget(P || 0, w, w * .05, w * .1) : '';
  $('#vCad').className = s.cad ? onTarget(Math.round(cad || 0), s.cad, 5, 10) : '';
  // the steps on the left: three done, the current one, the next ones
  if (planListIdx !== i) {
    planListIdx = i;
    const from = Math.max(0, i - 3);
    $('#plItems').innerHTML = Work.steps.slice(from, from + 12).map((x, k) => { const idx = from + k; return '<li class="' + (idx < i ? 'done' : idx === i ? 'cur' : '') + '"><span class="ic"></span><span>' + fmtTime(x.min * 60) + ', ' + (x.f != null ? gearLabel(x.f, x.r) : stepPower(x)) + '</span><span>' + (x.cad ? x.cad + ' ' + t('u.rpm') : '') + '</span></li>'; }).join('')
      + (from + 12 < n ? '<li><span class="ic"></span><span>' + t('plan.more', { n: n - from - 12 }) + '</span><span></span></li>' : '');
  }
  const total = Work.total();
  $('#plLeft').textContent = t('plan.toEnd', { t: fmtTime(Math.ceil(total - Work.t)) });
  $('#plProg').style.width = clamp(Work.t / total * 100, 0, 100).toFixed(1) + '%';
  $('#plFoot').textContent = Work.name == null ? t('plan.footer', { i: i + 1, n, p: zonePct(Work.ss) })
    : aimsAt(Work.steps) ? t('plan.footerW', { i: i + 1, n, p: zonePct(Work.ss) }) : t('plan.footerStep', { i: i + 1, n });
}
Records.addWorkout = function (ride, powerLog) {
  const D = this.data, news = [], now = ride.date;
  if (!ride.demo) {
    PEAKS.forEach(([k, sec, label]) => {
      if (powerLog.length < sec) return;
      let sum = 0, best = 0; for (let i = 0; i < powerLog.length; i++) { sum += powerLog[i]; if (i >= sec) sum -= powerLog[i - sec]; if (i >= sec - 1) best = Math.max(best, sum / sec); }
      best = Math.round(best); const old = D.peaks[k];
      if (best > 0 && (!old || best > old.w)) { D.peaks[k] = { w: best, date: now, route: ride.route, est: !ride.real }; news.push(t('rec.peak', { d: label, w: best }) + (ride.real ? '' : t('rec.est'))); }
    });
    if (!ride.wind && (!D.maxSpeed || ride.maxSpeed > D.maxSpeed.v)) { D.maxSpeed = { v: ride.maxSpeed, date: now, route: ride.route }; if (D.totals.rides) news.push(t('rec.maxSpeed', { v: fmt1(ride.maxSpeed) })); }
  }
  D.totals.rides++; D.totals.dist += ride.dist; D.totals.gain += ride.gain; D.totals.time += ride.time;
  D.history.unshift(ride); D.history = D.history.slice(0, 30);
  this.save(); this.push(ride, powerLog);
  return { news };
};
// Свободная езда: без финиша и соперников, завершается вручную
function finishFree() {
  if (phase !== 'race') return;
  const st = me.stats, t = raceT, km = st.dist / 1000;
  if (t < 60) { phase = 'done'; startMenu(); return; } // заезды короче минуты не сохраняем
  phase = 'done';
  const avgP = Math.round(st.sumP / Math.max(1, st.t));
  const ride = { id: Date.now().toString(36), date: Date.now(), kind: 'free', route: world.route.id, time: Math.round(t * 10) / 10, dist: Math.round(km * 100) / 100, avgSpeed: Math.round(km / Math.max(t / 3600, 1e-6) * 10) / 10, avgPower: avgP, real: st.real, demo: st.demoT > st.t * .5, maxSpeed: Math.round(st.maxV * 36) / 10, gain: Math.round(st.gain), avgCad: st.nCad ? Math.round(st.sumCad / st.nCad) : null, avgHR: st.nHR ? Math.round(st.sumHR / st.nHR) : null, place: 1, of: 1, char: settings.char, wind: rideWind };
  const rec = Records.addWorkout(ride, me.powerLog || []);
  $('#resTitle').textContent = tr('mode.free');
  $('#resSub').textContent = tr('res.freeSub', { route: world.route.name, n: me.lap + 1 });
  $('#resRec').innerHTML = rec.news.length ? '<b>' + tr('res.newRecords') + '</b><ul>' + rec.news.map(n => '<li>' + n + '</li>').join('') + '</ul>' : '';
  $('#resRec').classList.toggle('hidden', !rec.news.length);
  const sx = [[fmtTime(t), tr('res.time')], [fmt1(km) + ' ' + tr('u.km'), tr('res.dist')], [fmt1(ride.avgSpeed), tr('res.avgKmh')], [avgP + ' ' + tr('u.w'), st.real ? tr('res.avgPower') : tr('res.avgPowerEst')], [ride.avgCad || '—', tr('res.avgCad')], [ride.gain + ' ' + tr('u.m'), tr('rec.gain')]];
  if (st.nHR) sx.push([Math.round(st.sumHR / st.nHR) + ' / ' + st.maxHR, tr('res.hr')]);
  $('#resStats').innerHTML = sx.map(s => '<div class="stat"><div class="v">' + s[0] + '</div><div class="u">' + s[1] + '</div></div>').join('');
  $('#resList').innerHTML = '';
  $('#resM').classList.remove('hidden');
}
// The plan done, the ride goes on as a free one: nothing is saved, nor sent to the services, until the rider ends it
// from the pause menu, the time after the plan in it too (the maintainer, 2026-11-26). The trainer is let go of the
// plan's power: Work.target() gives none once the plan is over.
function planOver() {
  $('#target').classList.add('hidden');
  document.querySelectorAll('#plItems li.cur').forEach(li => li.classList.replace('cur', 'done'));
  $('#plLeft').textContent = t('plan.overLeft'); $('#plProg').style.width = '100%';
  $('#pauseHint').textContent = t('pause.planOver');
  updateModeUI(); toast(t('plan.over'), 8);
}
function finishWorkout() {
  phase = 'done';
  const st = me.stats, t = raceT, km = st.dist / 1000, zone = zonePct(Work.ss);
  const avgP = Math.round(st.sumP / Math.max(1, st.t));
  const ride = { id: Date.now().toString(36), date: Date.now(), kind: 'plan', route: world.route.id, time: Math.round(t * 10) / 10, dist: Math.round(km * 100) / 100, avgSpeed: Math.round(km / Math.max(t / 3600, 1e-6) * 10) / 10, avgPower: avgP, real: st.real, demo: st.demoT > st.t * .5, maxSpeed: Math.round(st.maxV * 36) / 10, gain: Math.round(st.gain), avgCad: st.nCad ? Math.round(st.sumCad / st.nCad) : null, avgHR: st.nHR ? Math.round(st.sumHR / st.nHR) : null, place: 1, of: 1, char: settings.char, wind: rideWind, steps: Work.steps.length, zone };
  const rec = Records.addWorkout(ride, me.powerLog || []);
  $('#resTitle').textContent = tr('res.workoutDone');
  const said = { name: Work.name, n: Work.steps.length, t: fmtTime(t), route: world.route.name, z: zone };
  $('#resSub').textContent = Work.name == null ? tr('res.planSub', said) : aimsAt(Work.steps) ? tr('res.icuSub', said) : tr('res.icuSubFree', said);
  $('#resRec').innerHTML = rec.news.length ? '<b>' + tr('res.newRecords') + '</b><ul>' + rec.news.map(n => '<li>' + n + '</li>').join('') + '</ul>' : '';
  $('#resRec').classList.toggle('hidden', !rec.news.length);
  const sx = [[fmtTime(t), tr('res.time')], [fmt1(km) + ' ' + tr('u.km'), tr('res.dist')], [fmt1(ride.avgSpeed), tr('res.avgKmh')], [avgP + ' ' + tr('u.w'), st.real ? tr('res.avgPower') : tr('res.avgPowerEst')], [ride.avgCad || '—', tr('res.avgCad')], [ride.gain + ' ' + tr('u.m'), tr('rec.gain')]];
  if (st.nHR) sx.push([Math.round(st.sumHR / st.nHR) + ' / ' + st.maxHR, tr('res.hr')]);
  $('#resStats').innerHTML = sx.map(s => '<div class="stat"><div class="v">' + s[0] + '</div><div class="u">' + s[1] + '</div></div>').join('');
  $('#resList').innerHTML = Work.steps.map((s, i) => { const x = Work.ss[i], avg = x.n ? Math.round(x.sumCad / x.n) : 0, z = x.aimed ? ', ' + Math.round(x.zone / x.aimed * 100) + '%' : '';
    // a gear step by its cadence; a workout's step by its power, against the target where it set one
    if (s.f != null) return '<li><span>' + (i + 1) + '</span><span>' + tr('res.stepRow', { g: gearLabel(s.f, s.r), c: s.cad, t: fmtTime(s.min * 60) }) + '</span><span>' + avg + ' ' + tr('u.rpm') + z + '</span></li>';
    return '<li><span>' + (i + 1) + '</span><span>' + escapeHTML(stepWhat(s)) + ', ' + fmtTime(s.min * 60) + '</span><span>' + Math.round(x.sumP / Math.max(x.time, 1e-6)) + ' ' + tr('u.w') + z + '</span></li>'; }).join('');
  setTimeout(() => $('#resM').classList.remove('hidden'), 1200);
}
