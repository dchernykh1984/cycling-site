'use strict';
/* ---- план во время заезда: подсказки и итоги (сам план выполняет заезд, js/ride.js) ---- */
let planListIdx = -2; // the step the list on the left was last drawn for
function updatePlanHUD(cad) {
  if (!Work.active || Work.idx < 0) return;
  const i = Work.idx, s = Work.steps[i], nx = Work.steps[i + 1], left = Work.ends[i] - Work.t, dur = s.min * 60, n = Work.steps.length;
  const [ft, rt] = gearTeeth(s.f, s.r);
  // the step's target beside the power
  $('#tTitle').textContent = t('plan.holdOn', { g: gearLabel(s.f, s.r), teeth: ft + '×' + rt });
  $('#tVal').textContent = s.cad;
  $('#tSub').textContent = nx ? t('plan.leftNext', { t: fmtTime(Math.ceil(left)), c: nx.cad }) : t('plan.leftLast', { t: fmtTime(Math.ceil(left)) });
  $('#tProg').style.width = clamp((dur - left) / dur * 100, 0, 100).toFixed(1) + '%';
  const d = Math.abs(Math.round(cad || 0) - s.cad); $('#vCad').className = d <= 5 ? 'act-ok' : d <= 10 ? 'act-near' : 'act-off';
  // the steps on the left: three done, the current one, the next ones
  if (planListIdx !== i) {
    planListIdx = i;
    const from = Math.max(0, i - 3);
    $('#plItems').innerHTML = Work.steps.slice(from, from + 12).map((x, k) => { const idx = from + k; return '<li class="' + (idx < i ? 'done' : idx === i ? 'cur' : '') + '"><span class="ic"></span><span>' + fmtTime(x.min * 60) + ', ' + gearLabel(x.f, x.r) + '</span><span>' + x.cad + ' ' + t('u.rpm') + '</span></li>'; }).join('')
      + (from + 12 < n ? '<li><span class="ic"></span><span>' + t('plan.more', { n: n - from - 12 }) + '</span><span></span></li>' : '');
  }
  const total = Work.total();
  $('#plLeft').textContent = t('plan.toEnd', { t: fmtTime(Math.ceil(total - Work.t)) });
  $('#plProg').style.width = clamp(Work.t / total * 100, 0, 100).toFixed(1) + '%';
  const zt = Work.ss.reduce((a, x) => a + x.zone, 0), at = Work.ss.reduce((a, x) => a + x.time, 0);
  $('#plFoot').textContent = t('plan.footer', { i: i + 1, n, p: at ? Math.round(zt / at * 100) : 0 });
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
    if (!D.maxSpeed || ride.maxSpeed > D.maxSpeed.v) { D.maxSpeed = { v: ride.maxSpeed, date: now, route: ride.route }; if (D.totals.rides) news.push(t('rec.maxSpeed', { v: fmt1(ride.maxSpeed) })); }
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
  const ride = { id: Date.now().toString(36), date: Date.now(), kind: 'free', route: world.route.id, time: Math.round(t * 10) / 10, dist: Math.round(km * 100) / 100, avgSpeed: Math.round(km / Math.max(t / 3600, 1e-6) * 10) / 10, avgPower: avgP, real: st.real, demo: st.demoT > st.t * .5, maxSpeed: Math.round(st.maxV * 36) / 10, gain: Math.round(st.gain), avgCad: st.nCad ? Math.round(st.sumCad / st.nCad) : null, avgHR: st.nHR ? Math.round(st.sumHR / st.nHR) : null, place: 1, of: 1, char: settings.char };
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
function finishWorkout() {
  phase = 'done';
  const st = me.stats, t = raceT, km = st.dist / 1000;
  const zoneT = Work.ss.reduce((a, x) => a + x.zone, 0), allT = Work.ss.reduce((a, x) => a + x.time, 0), zonePct = allT ? Math.round(zoneT / allT * 100) : 0;
  const avgP = Math.round(st.sumP / Math.max(1, st.t));
  const ride = { id: Date.now().toString(36), date: Date.now(), kind: 'plan', route: world.route.id, time: Math.round(t * 10) / 10, dist: Math.round(km * 100) / 100, avgSpeed: Math.round(km / Math.max(t / 3600, 1e-6) * 10) / 10, avgPower: avgP, real: st.real, demo: st.demoT > st.t * .5, maxSpeed: Math.round(st.maxV * 36) / 10, gain: Math.round(st.gain), avgCad: st.nCad ? Math.round(st.sumCad / st.nCad) : null, avgHR: st.nHR ? Math.round(st.sumHR / st.nHR) : null, place: 1, of: 1, char: settings.char, steps: Work.steps.length, zone: zonePct };
  const rec = Records.addWorkout(ride, me.powerLog || []);
  $('#resTitle').textContent = tr('res.workoutDone');
  $('#resSub').textContent = tr('res.planSub', { n: Work.steps.length, t: fmtTime(t), route: world.route.name, z: zonePct });
  $('#resRec').innerHTML = rec.news.length ? '<b>' + tr('res.newRecords') + '</b><ul>' + rec.news.map(n => '<li>' + n + '</li>').join('') + '</ul>' : '';
  $('#resRec').classList.toggle('hidden', !rec.news.length);
  const sx = [[fmtTime(t), tr('res.time')], [fmt1(km) + ' ' + tr('u.km'), tr('res.dist')], [fmt1(ride.avgSpeed), tr('res.avgKmh')], [avgP + ' ' + tr('u.w'), st.real ? tr('res.avgPower') : tr('res.avgPowerEst')], [ride.avgCad || '—', tr('res.avgCad')], [ride.gain + ' ' + tr('u.m'), tr('rec.gain')]];
  if (st.nHR) sx.push([Math.round(st.sumHR / st.nHR) + ' / ' + st.maxHR, tr('res.hr')]);
  $('#resStats').innerHTML = sx.map(s => '<div class="stat"><div class="v">' + s[0] + '</div><div class="u">' + s[1] + '</div></div>').join('');
  $('#resList').innerHTML = Work.steps.map((s, i) => { const x = Work.ss[i], avg = x.n ? Math.round(x.sumCad / x.n) : 0, z = x.time ? Math.round(x.zone / x.time * 100) : 0;
    return '<li><span>' + (i + 1) + '</span><span>' + tr('res.stepRow', { g: gearLabel(s.f, s.r), c: s.cad, t: fmtTime(s.min * 60) }) + '</span><span>' + avg + ' ' + tr('u.rpm') + ', ' + z + '%</span></li>'; }).join('');
  setTimeout(() => $('#resM').classList.remove('hidden'), 1200);
}
