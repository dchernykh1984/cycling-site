'use strict';
/* ---------------- Strava live segments: the member's starred segments on the route, against their own times ---------------- */
// What the member allowed at Strava is read for their own page alone (Strava's API agreement): their starred segments,
// each one's line, their own times on it and their best effort's pace. The site keeps none of it; the page keeps it
// in memory for the visit. A segment the route rides -- its start, its end ahead and its line between them along the
// route -- is timed from its start to its end in the route's metres, every lap of a loop, and shown in a window beside
// the road as a bike computer shows one: the fields the member ticked in the setup.
// The fields, in the window's order: [key, its words, on for a member who has not chosen]
const SEG_FIELDS = [
  ['time', () => t('seg.f.time'), true],
  ['gapBest', () => t('seg.f.gapBest'), true],
  ['left', () => t('seg.f.left'), true],
  ['done', () => t('seg.f.done'), false],
  ['place', () => t('seg.f.place'), true],
  ['gapAhead', () => t('seg.f.gapAhead'), false],
  ['projected', () => t('seg.f.projected'), false],
  ['best', () => t('seg.f.best'), true],
  ['grade', () => t('seg.f.grade'), false],
  ['speed', () => t('seg.f.speed'), false],
  ['power', () => t('seg.f.power'), false],
  ['profile', () => t('seg.f.profile'), true]
];
const SEG_NEAR_M = 30;     // a segment's line and the route's this close are one road: a ride's GPS and the map apart
const SEG_LINE_M = 45;     // between its ends, its line this close to the route's all along
const SEG_STEP_M = 4;      // how finely the route is searched for a segment's ends
const SEG_SOON_M = 500;    // the window comes up this far before a segment's start
const SEG_RESULT_S = 12;   // and shows its result this long after its end
const SEG_MIN_M = 50;      // a segment shorter than this is no stretch to race
const segOn = () => !!(settings.segments && settings.segments.on);
const segField = k => { const f = (settings.segments && settings.segments.fields) || {}; return k in f ? !!f[k] : SEG_FIELDS.find(x => x[0] === k)[2]; };
const segAllowed = () => !!(Records.me && Records.me.authenticated && Records.me.strava_segments);
const segLength = m => m >= 1000 ? fmt1(m / 1000) + ' ' + t('u.km') : Math.round(m) + ' ' + t('u.m');
const segGap = s => (s < 0 ? '−' : '+') + fmtTime(Math.abs(Math.round(s)));

// a segment's point d metres from its start, on its own line: { x, z } in the route's metres
function segAt(P, d) {
  let i = 1; while (i < P.length - 1 && P[i].d < d) i++;
  const a = P[i - 1], b = P[i], f = clamp((d - a.d) / ((b.d - a.d) || 1), 0, 1);
  return { x: a.x + (b.x - a.x) * f, z: a.z + (b.z - a.z) * f };
}
// the segments of the member's starred list whose start and end both lie by the route: the ones worth reading
function segCandidates(T, list) {
  return (list || []).filter(s => {
    const a = proj(s.start[0], s.start[1], T.origin), b = proj(s.end[0], s.end[1], T.origin);
    return s.distance_m >= SEG_MIN_M && routeGap(T, a.x, a.z) < SEG_NEAR_M && routeGap(T, b.x, b.z) < SEG_NEAR_M;
  });
}
// Where a segment lies on the route: each pass of its start, its end ahead of it within half again its length, and its
// line between them along the route's all the way -- so a road ridden out and back takes it the way it was ridden.
// [{ s0, len }] in the route's metres; a loop's s0 within one lap.
function segPlaces(T, seg) {
  const P = seg.points.map(p => { const q = proj(p[0], p[1], T.origin); return { x: q.x, z: q.z, d: p[3] }; });
  const Ls = seg.distance_m || P[P.length - 1].d, A = P[0], B = P[P.length - 1], o = {}, out = [];
  if (Ls < SEG_MIN_M) return out;
  const gap = (s, p) => { sampleAt(T, s, o); return Math.hypot(o.x - p.x, o.z - p.z); };
  const pass = s0 => {
    const to = T.loop ? s0 + Ls * 1.5 : Math.min(T.L, s0 + Ls * 1.5); let end = null, endD = SEG_NEAR_M;
    for (let s = s0 + Ls * .6; s <= to; s += SEG_STEP_M) { const d = gap(s, B); if (d < endD) { endD = d; end = s; } }
    if (end == null) return;
    const len = end - s0;
    for (let k = 1; k < 20; k++) if (gap(s0 + len * k / 20, segAt(P, Ls * k / 20)) > SEG_LINE_M) return;
    const at = T.loop ? ((s0 % T.L) + T.L) % T.L : s0;
    // a loop's start line may split one pass in two, at its end and at its start
    if (!out.some(x => Math.abs(x.s0 - at) < SEG_MIN_M || (T.loop && T.L - Math.abs(x.s0 - at) < SEG_MIN_M))) out.push({ s0: at, len });
  };
  let runS = null, runD = SEG_NEAR_M;
  for (let s = 0; s <= T.L; s += SEG_STEP_M) {
    const d = gap(s, A);
    if (d < SEG_NEAR_M) { if (d < runD) { runD = d; runS = s; } }
    else if (runS != null) { pass(runS); runS = null; runD = SEG_NEAR_M; }
  }
  if (runS != null) pass(runS);
  return out;
}
// the best effort's time d metres into the segment, from its pace; without it its time spread evenly; null without one
function segBestAt(m, d) {
  const b = m.d.best, total = b ? b.elapsed_s : m.seg.pr_s; if (!total) return null;
  const T = b && b.times; if (!T || T.length < 2) return total * clamp(d / m.Ls, 0, 1);
  let i = 1; while (i < T.length - 1 && T[i][0] < d) i++;
  const a = T[i - 1], c = T[i], f = clamp((d - a[0]) / ((c[0] - a[0]) || 1), 0, 1);
  return a[1] + (c[1] - a[1]) * f;
}
// how far into the segment the best effort was after t seconds: the ghost on its profile
function segBestDist(m, t) {
  const b = m.d.best, total = b ? b.elapsed_s : m.seg.pr_s; if (!total) return null;
  const T = b && b.times; if (!T || T.length < 2) return m.Ls * clamp(t / total, 0, 1);
  let i = 1; while (i < T.length - 1 && T[i][1] < t) i++;
  const a = T[i - 1], c = T[i], f = clamp((t - a[1]) / ((c[1] - a[1]) || 1), 0, 1);
  return a[0] + (c[0] - a[0]) * f;
}
const Segs = {
  list: null, listing: null, failed: null, details: new Map(), places: new Map(), tracks: new Map(),
  on: [], gen: 0, result: null,
  // the member's starred segments, read once a visit; a failure is said and asked again next time
  starred() {
    if (this.list) return Promise.resolve(this.list);
    if (!this.listing) this.listing = Site.get('/strava/segments').then(l => { this.list = l; this.failed = null; return l; })
      .catch(e => { this.failed = e.message; return null; }).finally(() => { this.listing = null; });
    return this.listing;
  },
  detail(id) {
    if (!this.details.has(id)) this.details.set(id, Site.get('/strava/segments/' + id).catch(e => { this.details.delete(id); throw e; }));
    return this.details.get(id);
  },
  // the segments the route about to be ridden takes, timed from its start
  async prepare(w) {
    const gen = ++this.gen; this.on = []; this.result = null;
    if (!segOn() || !segAllowed()) return;
    const list = await this.starred(); if (gen !== this.gen || !list) return;
    const found = await Promise.all(segCandidates(w.T, list).map(s => this.detail(s.id).then(d => ({ s, d })).catch(() => null)));
    if (gen !== this.gen) return;
    found.filter(Boolean).forEach(({ s, d }) => {
      const key = w.route.id + ':' + s.id; if (!this.places.has(key)) this.places.set(key, segPlaces(w.T, d));
      const Ls = d.distance_m || s.distance_m;
      this.places.get(key).forEach(p => this.on.push({ seg: s, d, s0: p.s0, len: p.len, Ls, scale: p.len / Ls, run: null }));
    });
  },
  stop() { this.gen++; this.on = []; this.result = null; },
  // the next start of a segment after the route's metre s: each lap's on a loop
  next(m, s) { const T = world.T; return T.loop ? m.s0 + (Math.floor((s - m.s0) / T.L) + 1) * T.L : m.s0; },
  // the rider went from `from` to `to` in dt seconds: their tries on the segments, started, timed and finished
  step(from, to, dt, inp) {
    const ds = to - from;
    for (const m of this.on) {
      const r = m.run;
      if (r && to < r.at) m.run = null; // brought back to the start of a route: that try is off
      else if (r) {
        const end = r.at + m.len, part = to >= end && ds > 0 ? (end - from) / ds : 1;
        r.t += dt * part; r.sumP += (inp.P || 0) * dt * part;
        if (to >= end) { this.finish(m, r); m.run = null; }
      }
      if (!m.run) {
        const at = this.next(m, from);
        if (from < at && to >= at && ds > 0) { const part = (to - at) / ds; m.run = { at, t: dt * part, sumP: (inp.P || 0) * dt * part }; }
      }
    }
  },
  finish(m, r) {
    const best = m.d.best ? m.d.best.elapsed_s : m.seg.pr_s, efforts = m.d.efforts;
    this.result = { m, t: r.t, best, place: efforts ? 1 + efforts.filter(e => e < r.t).length : null, of: efforts ? efforts.length + 1 : null,
      power: r.t > 0 ? r.sumP / r.t : 0, speed: r.t > 0 ? m.Ls / r.t : 0, until: raceT + SEG_RESULT_S };
    const words = { name: m.seg.name, t: fmtTime(r.t) };
    if (!best) toast(t('seg.done', words), 5);
    else if (r.t < best) toast(t('seg.doneFaster', Object.assign(words, { d: fmtTime(Math.round(best - r.t)) })), 5);
    else toast(t('seg.doneSlower', Object.assign(words, { d: fmtTime(Math.round(r.t - best)) })), 5);
  },
  // what the window shows now: a try under way, a result just in, or the segment ahead
  pick() {
    const run = this.on.find(m => m.run); if (run) return { kind: 'run', m: run };
    if (this.result && raceT < this.result.until) return { kind: 'result', m: this.result.m };
    let soon = null;
    for (const m of this.on) { const ahead = this.next(m, me.s) - me.s; if (ahead > 0 && ahead <= SEG_SOON_M && (!soon || ahead < soon.ahead)) soon = { kind: 'soon', m, ahead }; }
    return soon;
  }
};
// the rows of the window for what it shows: [label, value, how it reads (ahead, behind or plain)]
function segRows(p) {
  const m = p.m, rows = [], best = m.d.best ? m.d.best.elapsed_s : m.seg.pr_s, efforts = m.d.efforts;
  const add = (k, v, c) => { if (segField(k) && v != null) rows.push([SEG_FIELDS.find(x => x[0] === k)[1](), v, c || '']); };
  if (p.kind === 'soon') {
    rows.push([t('seg.soon'), segLength(p.ahead), 'big']);
    rows.push([t('seg.length'), segLength(m.Ls) + ', ' + fmtPct(m.seg.average_grade), '']);
    add('best', best ? fmtTime(best) : efforts === null ? t('seg.noSub') : t('seg.noBest'));
    return rows;
  }
  if (p.kind === 'result') {
    const res = Segs.result;
    rows.push([t('seg.finished'), fmtTime(res.t), 'big']);
    if (best) add('gapBest', segGap(res.t - best), res.t < best ? 'ahead' : 'behind');
    if (res.place) add('place', t('seg.placeOf', { p: res.place, n: res.of }));
    add('speed', fmt1(res.speed * 3.6) + ' ' + t('u.kmh')); add('power', Math.round(res.power) + ' ' + t('u.w'));
    return rows;
  }
  const r = m.run, d = clamp((me.s - r.at) / m.scale, 0, m.Ls), at = segBestAt(m, d);
  // the finish foreseen: the time so far and what the best effort took from here
  const projected = at != null ? r.t + (best - at) : null;
  add('time', fmtTime(r.t), 'big');
  if (at != null) add('gapBest', segGap(r.t - at), r.t < at ? 'ahead' : 'behind');
  add('left', segLength(m.Ls - d)); add('done', segLength(d));
  if (efforts && projected != null) {
    const faster = efforts.filter(e => e < projected), place = faster.length + 1;
    add('place', t('seg.placeOf', { p: place, n: efforts.length + 1 }));
    add('gapAhead', faster.length ? segGap(projected - faster[faster.length - 1]) : t('seg.first'), faster.length ? 'behind' : 'ahead');
  }
  if (projected != null) add('projected', fmtTime(projected));
  add('best', best ? fmtTime(best) : efforts === null ? t('seg.noSub') : t('seg.noBest'));
  add('grade', fmtPct(gradeAt(world.T, me.s) * 100));
  add('speed', r.t > 1 ? fmt1(d / r.t * 3.6) + ' ' + t('u.kmh') : null); add('power', r.t > 1 ? Math.round(r.sumP / r.t) + ' ' + t('u.w') : null);
  return rows;
}
// the segment's profile from its own heights: the rider on it and, where there is one, the best effort's ghost
function segProfile(cv, p) {
  const m = p.m, P = m.d.points, dpr = Math.min(window.devicePixelRatio || 1, 2), w = cv.clientWidth || 200, h = cv.clientHeight || 46;
  if (cv.width !== Math.round(w * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
  const g = cv.getContext('2d'), W = cv.width, H = cv.height; g.clearRect(0, 0, W, H);
  let mn = Infinity, mx = -Infinity; P.forEach(q => { mn = Math.min(mn, q[2]); mx = Math.max(mx, q[2]); });
  const span = Math.max(10, mx - mn), X = d => d / m.Ls * W, Y = y => H - 3 * dpr - (y - mn) / span * (H - 8 * dpr);
  const yAt = d => { let i = 1; while (i < P.length - 1 && P[i][3] < d) i++; const a = P[i - 1], b = P[i], f = clamp((d - a[3]) / ((b[3] - a[3]) || 1), 0, 1); return a[2] + (b[2] - a[2]) * f; };
  g.beginPath(); g.moveTo(0, H); P.forEach(q => g.lineTo(X(q[3]), Y(q[2]))); g.lineTo(W, H); g.closePath(); g.fillStyle = 'rgba(252,76,2,.35)'; g.fill();
  g.lineWidth = 1.5 * dpr; g.strokeStyle = 'rgba(243,246,249,.85)'; g.beginPath(); P.forEach((q, i) => i ? g.lineTo(X(q[3]), Y(q[2])) : g.moveTo(X(q[3]), Y(q[2]))); g.stroke();
  const dot = (d, c, r) => { g.fillStyle = c; g.beginPath(); g.arc(X(d), Y(yAt(d)), r * dpr, 0, 7); g.fill(); };
  if (p.kind !== 'run') { dot(p.kind === 'soon' ? 0 : m.Ls, '#ffffff', 4); return; }
  const ghost = segBestDist(m, m.run.t); if (ghost != null) dot(ghost, 'rgba(243,246,249,.75)', 4);
  const d = clamp((me.s - m.run.at) / m.scale, 0, m.Ls); dot(d, '#ffffff', 5.5); dot(d, '#FC4C02', 3.5);
}
// the window beside the road, redrawn with the HUD
function segHUD() {
  const box = $('#segBox'), p = world && segOn() ? Segs.pick() : null;
  box.classList.toggle('hidden', !p); $('#hud').classList.toggle('seg-on', !!p); if (!p) return;
  $('#segName').textContent = p.m.seg.name;
  $('#segRows').innerHTML = segRows(p).map(r => '<div class="' + r[2] + '"><dt>' + escapeHTML(r[0]) + '</dt><dd>' + escapeHTML(r[1]) + '</dd></div>').join('');
  const cv = $('#segProf'), prof = segField('profile'); cv.classList.toggle('hidden', !prof); if (prof) segProfile(cv, p);
}

/* ---- the setup: the box, its fields, and whether the member's Strava lets it work ---- */
function renderSegments() {
  const s = settings.segments || {}; $('#segOn').checked = !!s.on;
  $('#segOpts').classList.toggle('hidden', !s.on);
  const box = $('#segFields');
  if (!box.children.length) box.innerHTML = SEG_FIELDS.map(f => '<label class="chk"><input type="checkbox" data-seg="' + f[0] + '"> <span>' + escapeHTML(f[1]()) + '</span></label>').join('');
  box.querySelectorAll('input').forEach(i => { i.checked = segField(i.dataset.seg); });
  renderSegState();
}
function readSegments() {
  const fields = {}; $('#segFields').querySelectorAll('input').forEach(i => { fields[i.dataset.seg] = i.checked; });
  settings.segments = { on: $('#segOn').checked, fields };
}
// a line under the box: what the member needs first, or how many of their segments the chosen route takes
function renderSegState() {
  const el = $('#segState'); el.textContent = '';
  if (!segOn()) return;
  const who = Records.me, link = (href, words) => { const a = document.createElement('a'); a.href = href; a.target = '_top'; a.textContent = words; return a; };
  if (!who || !who.authenticated) { el.append(t('seg.signIn') + ' ', link(Site.loginHref(), t('seg.signInLink'))); return; }
  if (!who.strava_available) { el.textContent = t('seg.unavailable'); return; }
  if (!who.strava_segments) { el.append(t('seg.allow') + ' ', link(langPath(who.strava_segments_url) + '&next=' + encodeURIComponent(topPath()), t('seg.allowLink'))); return; }
  if (Segs.failed) { el.textContent = t('seg.failed', { msg: Segs.failed }); return; }
  if (!Segs.list) { el.textContent = t('seg.loading'); Segs.starred().then(() => { if (segOn()) renderSegState(); }); return; }
  const r = ROUTES.find(x => x.id === routeSel) || ROUTES[0];
  if (!Segs.tracks.has(r.id)) Segs.tracks.set(r.id, buildTrack(r));
  const found = segCandidates(Segs.tracks.get(r.id), Segs.list);
  el.textContent = found.length ? t('seg.onRoute', { n: found.length, list: found.map(s => s.name).join(', ') }) : t('seg.noneOnRoute', { n: Segs.list.length });
}
