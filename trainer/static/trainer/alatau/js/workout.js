'use strict';
/* ---- план во время заезда: подсказки и итоги (сам план выполняет заезд, js/ride.js) ---- */
function updatePlanHUD(cad) {
  if (!Work.active || Work.idx < 0) return;
  const i = Work.idx, s = Work.steps[i], nx = Work.steps[i + 1], left = Work.ends[i] - Work.t, dur = s.min * 60;
  const [ft, rt] = gearTeeth(s.f, s.r);
  $('#wStep').textContent = t('plan.stepOf', { i: i + 1, n: Work.steps.length });
  $('#wLeft').textContent = t('plan.left', { t: fmtTime(Math.ceil(left)) });
  $('#wGear').textContent = gearLabel(s.f, s.r); $('#wTeeth').textContent = t('plan.teeth', { g: ft + '×' + rt });
  $('#wCad').textContent = s.cad;
  const a = Math.round(cad || 0), d = Math.abs(a - s.cad), act = $('#wAct');
  act.textContent = a; act.className = 'v ' + (d <= 5 ? 'ok' : d <= 10 ? 'near' : 'off');
  $('#wProg').style.width = clamp((dur - left) / dur * 100, 0, 100).toFixed(1) + '%';
  $('#wNext').textContent = nx ? t('plan.next', { g: gearLabel(nx.f, nx.r), c: nx.cad, t: fmtTime(nx.min * 60) }) : t('plan.last');
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
