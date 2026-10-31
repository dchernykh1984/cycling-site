'use strict';
/* ---------------- Рекорды: личный кабинет на сайте (для вошедших) или этот браузер ---------------- */
const PEAKS = [5, 60, 300, 1200].map(sec => ['p' + sec, sec, durLabel(sec)]);
const fmtDate = d => d ? new Date(d).toLocaleDateString(LOCALE, { day: 'numeric', month: 'short', year: 'numeric' }) : '—';
const Records = {
  data: null, synced: false, me: null, loginUrl: '', accountUrl: '',
  empty() { return { v: 1, routes: {}, peaks: {}, maxSpeed: null, totals: { rides: 0, dist: 0, gain: 0, time: 0 }, history: [] }; },
  load() {
    const d = store.get('records', null); this.data = d ? Object.assign(this.empty(), d) : this.empty();
    ROUTES.forEach(r => { const pb = store.get('pb:' + r.id, null); if (pb && !this.data.routes[r.id]) this.data.routes[r.id] = { time: pb, date: null, attempts: 1 }; });
  },
  async connect() {
    try {
      const me = await Site.get('/me'); this.me = me; this.loginUrl = langPath(me.login_url || '');
      if (!me.authenticated) return;
      this.synced = true; this.accountUrl = langPath(me.profile_url || ''); renderStravaNote();
      await this.pull(); renderMenu();
      if (!$('#recM').classList.contains('hidden')) renderRecords();
    } catch (e) { this.me = null; }
  },
  // сводка и история из личного кабинета; план тренировки остаётся свой
  async pull() {
    const [sum, rides] = await Promise.all([Site.get('/records'), Site.get('/rides?limit=30')]);
    this.data = recordsFromServer(sum, rides, this.data && this.data.plan); store.set('records', this.data);
  },
  // завершённый заезд уходит в личный кабинет; рекорды считает сервер по всем заездам участника
  push(ride, powerLog) {
    if (!this.synced) return;
    const peaks = bestPeaks(powerLog || []), num = (v, lo, hi) => (v == null || isNaN(v)) ? null : Math.round(clamp(v, lo, hi));
    const body = {
      route: ride.route, route_name: routeName(ride.route), kind: ride.kind || 'race', group_id: ride.group && groupRide ? groupRide.gid : null,
      duration_s: Math.max(1, ride.time), distance_m: Math.round(clamp(ride.dist * 1000, 0, 1e6)), elevation_gain_m: clamp(ride.gain || 0, 0, 20000),
      avg_speed_kmh: clamp(ride.avgSpeed || 0, 0, 120), max_speed_kmh: clamp(ride.maxSpeed || 0, 0, 150), avg_power_w: num(ride.avgPower, 0, 3000),
      avg_cadence_rpm: num(ride.avgCad, 0, 250), avg_hr_bpm: num(ride.avgHR, 0, 260), max_hr_bpm: me && me.stats && me.stats.maxHR ? num(me.stats.maxHR, 0, 260) : null,
      power_source: ride.demo ? 'demo' : ride.real ? 'measured' : 'estimated', place: ride.of > 1 ? ride.place : null, field_size: ride.of > 1 ? ride.of : null,
      peak_5s_w: num(peaks.p5, 0, 3000), peak_1m_w: num(peaks.p60, 0, 3000), peak_5m_w: num(peaks.p300, 0, 3000), peak_20m_w: num(peaks.p1200, 0, 3000),
      track: !ride.demo && me && me.track && me.track.length > 1 ? me.track : null
    };
    Site.post('/rides', body)
      .then(res => { if (phase === 'done') { showServerRecords(res.records, ride, peaks); stravaShow(res.ride.id, res.strava); } return this.pull(); })
      .then(() => { if (phase === 'menu') renderMenu(); })
      .catch(e => { const box = $('#resRec'); box.innerHTML = '<b>' + t('rec.notSaved') + '</b><ul><li>' + escapeHTML(e.message) + '</li></ul>'; box.classList.remove('hidden'); });
  },
  save() { store.set('records', this.data); return Promise.resolve(); },
  best(routeId) { const r = this.data && this.data.routes[routeId]; return r && r.time ? r.time : null; },
  add(ride, powerLog) {
    const D = this.data, news = [], now = ride.date;
    const prev = D.routes[ride.route];
    const rr = prev ? Object.assign({}, prev) : { attempts: 0 };
    rr.attempts = (rr.attempts || 0) + 1;
    if (!prev || !prev.time || ride.time < prev.time) {
      news.push(prev && prev.time ? t('rec.bestFaster', { t: fmtTime(ride.time), d: fmtTime(prev.time - ride.time) }) : t('rec.first', { t: fmtTime(ride.time) }));
      Object.assign(rr, { time: ride.time, date: now, char: ride.char, demo: ride.demo, place: ride.place, of: ride.of });
    }
    if (!ride.demo) {
      if (ride.avgPower > (rr.avgPower || 0)) { if (prev && prev.avgPower) news.push(t('rec.avgPower', { w: ride.avgPower })); rr.avgPower = ride.avgPower; }
      PEAKS.forEach(([k, sec, label]) => {
        if (powerLog.length < sec) return;
        let sum = 0, best = 0; for (let i = 0; i < powerLog.length; i++) { sum += powerLog[i]; if (i >= sec) sum -= powerLog[i - sec]; if (i >= sec - 1) best = Math.max(best, sum / sec); }
        best = Math.round(best); const old = D.peaks[k];
        if (best > 0 && (!old || best > old.w)) { D.peaks[k] = { w: best, date: now, route: ride.route, est: !ride.real }; news.push(t('rec.peak', { d: label, w: best }) + (ride.real ? '' : t('rec.est'))); }
      });
    }
    if (ride.avgSpeed > (rr.avgSpeed || 0)) rr.avgSpeed = ride.avgSpeed;
    D.routes[ride.route] = rr;
    if (!ride.demo && (!D.maxSpeed || ride.maxSpeed > D.maxSpeed.v)) { D.maxSpeed = { v: ride.maxSpeed, date: now, route: ride.route }; if (D.totals.rides) news.push(t('rec.maxSpeed', { v: fmt1(ride.maxSpeed) })); }
    D.totals.rides++; D.totals.dist += ride.dist; D.totals.gain += ride.gain; D.totals.time += ride.time;
    D.history.unshift(ride); D.history = D.history.slice(0, 30);
    this.save(); this.push(ride, powerLog);
    return { news, prev };
  },
  reset() { this.data = this.empty(); ROUTES.forEach(r => store.set('pb:' + r.id, null)); return this.save(); }
};
const routeName = id => (ROUTES.find(r => r.id === id) || { name: id }).name;
// a group race in the language of the page when the page knows its route, else as its host named it
const routeTitle = g => ROUTES.some(r => r.id === g.route) ? routeName(g.route) : (g.route_name || g.route);
function renderRecords() {
  const D = Records.data, T = D.totals;
  $('#recSync').textContent = Records.synced ? t('records.synced') : t('records.local');
  if (!Records.synced && Records.loginUrl) { const a = document.createElement('a'); a.href = Site.loginHref(); a.target = '_top'; a.textContent = ' ' + t('signIn'); $('#recSync').appendChild(a); }
  if (Records.synced && Records.accountUrl) { const a = document.createElement('a'); a.href = Records.accountUrl + '#virtual-rides'; a.target = '_top'; a.textContent = ' ' + t('openProfile'); $('#recSync').appendChild(a); }
  const tile = (v, u) => '<div class="stat"><div class="v">' + v + '</div><div class="u">' + u + '</div></div>';
  $('#recTotals').innerHTML = tile(T.rides, tn('rides', T.rides)) + tile(fmt1(T.dist) + ' ' + t('u.km'), t('rec.totalDist')) + tile(Math.round(T.gain) + ' ' + t('u.m'), t('rec.gain')) + tile(fmtTime(T.time), t('rec.saddle'));
  $('#recPeaks').innerHTML = PEAKS.map(([k, , label]) => { const p = D.peaks[k]; return tile(p ? p.w + ' ' + t('u.w') : '—', label + (p && p.est ? t('rec.estShort') : '')); }).join('') + tile(D.maxSpeed ? fmt1(D.maxSpeed.v) + ' ' + t('u.kmh') : '—', t('rec.topSpeed'));
  $('#recRoutes').innerHTML = ROUTES.map(r => {
    const x = D.routes[r.id];
    return '<div class="rrow"><div><b>' + r.name + '</b><small>' + (x && x.time ? fmtDate(x.date) + (x.demo ? t('rec.demo') : '') + t('rec.attempts', { n: x.attempts }) : t('rec.notYet')) + '</small></div><div class="rv">' + (x && x.time ? fmtTime(x.time) : '—') + (x && x.avgPower ? '<small>' + t('rec.avgW', { w: x.avgPower }) + '</small>' : '') + '</div></div>';
  }).join('');
  $('#recHist').innerHTML = D.history.length ? D.history.slice(0, 12).map(h => '<li><span>' + fmtDate(h.date) + '</span><span>' + (h.kind === 'plan' ? t('hist.plan') : h.kind === 'free' ? t('hist.free') : '') + routeName(h.route) + (h.of > 1 ? t('hist.place', { p: h.place, n: h.of }) : '') + (h.demo ? t('rec.demo') : '') + '</span><span>' + fmtTime(h.time) + '<small>' + fmt1(h.avgSpeed) + ' ' + t('u.kmh') + ', ' + h.avgPower + ' ' + t('u.w') + '</small></span></li>').join('') : '<li class="empty">' + t('hist.empty') + '</li>';
  const rb = $('#btnRecReset'); rb.textContent = t('records.reset'); rb.dataset.armed = ''; rb.classList.toggle('hidden', !!Records.synced);
}
