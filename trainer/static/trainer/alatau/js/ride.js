'use strict';
/* ---------------- Заезд: состояние и шаг ---------------- */
// The ride itself, apart from its drawing: nothing here reads the page or draws. Each frame the ride
// takes a step; the scene and the HUD are then drawn from its state, and what happened during the
// step reaches the page through rideHooks.
let world = null; // the course being ridden (js/track.js)
let phase = 'loading', bots = [], me = null, raceT = 0, cdT = 0;
let rideMode = 'race';  // режим текущего заезда: race | plan | free
let rideWind = null; // the wind of the ride under way, { ms, from }: a group race's, else the rider's own when on
// what the page does when something happens in the ride: go, lap, backToStart, sight, finish, planStep, planSoon, planDone
const rideHooks = {};
function rideEvent(type, ...args) { const f = rideHooks[type]; if (f) f(...args); }
// rho and draft are the air a rider is in: sea level and no wake until the ride's step sets them (airAround)
function newRider(name, color, mass, s, lane) { return { name, color, mass, v: 0, s, lane, CdA: PHYS.CdA, rho: airDensity(0), draft: 0, phase: Math.random() * 6, finishT: null, P: 0 }; }
// The bikes as drawn (js/riders.js) are 1.71 m from tyre to tyre: two riders' points that far apart leave no gap
const BIKE_LENGTH = 1.71;
// The rules of a race with protocols being ridden (specs/495-virtual-race) -- its mode, whether categories draft each
// other, and the rider's bib, category and laps -- or null; the page keeps them (js/group-ride.js)
const raceRules = () => (typeof groupRide !== 'undefined' && groupRide && groupRide.race) || null;
// the share of r's drag that o's wake takes, o being anyone on the road: on a loop the one just behind is a lap ahead.
// In a race with protocols a time trial has nobody's wake, and a group race whose maker said so none across
// categories; the rider ahead's size counts (draftScale).
function wakeOf(r, o) {
  if (o === r) return 0;
  const rules = raceRules();
  if (rules && (rules.mode === 'itt' || (!rules.draftBetween && (o.group || '') !== (r.group || '')))) return 0;
  const T = world.T; let d = o.s - r.s; if (T.loop) d = ((d % T.L) + T.L) % T.L;
  return draftShare(d - BIKE_LENGTH, o.lane - r.lane) * draftScale(o.CdA, r.CdA);
}
// the air a rider rides in this step: its density at their height y, the best wake among the riders ahead and the
// wind along their way
const _wa = {};
function airAround(r, y) {
  const o = sampleAt(world.T, r.s, _wa); r.tail = tailwind(rideWind, o.tx, o.tz);
  r.rho = airDensity(y); r.draft = wakeOf(r, me);
  for (const b of bots) r.draft = Math.max(r.draft, wakeOf(r, b));
}
// a rider at the start of a ride: nothing ridden yet
function startRider(r) {
  r.stats = { dist: 0, gain: 0, sumP: 0, sumCad: 0, nCad: 0, maxV: 0, t: 0, sumHR: 0, nHR: 0, maxHR: 0, real: false, demoT: 0 };
  r.powerLog = []; r.pAcc = 0; r.pT = 0; r.track = []; r.rr = []; r.lap = 0;
  return r;
}
const MAX_TRACK = 6 * 3600; // the site keeps six hours of a ride's track, a point a second
const MAX_RR = 6 * 3600 * 220 / 60; // and six hours of RR intervals at 220 beats a minute (api: _MAX_RR)
// the strap's RR intervals since the last frame, kept when "Write HRV" is on: a heart at 27 to 270 beats a minute
function keepRR(r, rr) { if (settings.hrv) for (const ms of rr || []) if (ms >= 220 && ms <= 2500 && r.rr.length < MAX_RR) r.rr.push(ms); }
// [t_s, lat, lon, ele_m, distance_m, speed_ms, power_w, cadence_rpm, hr_bpm]: the route's place on the map, not a GPS fix
function trackPoint(inp) {
  const o = riderPos(me, {}), ll = unproj(o.px, o.pz, world.T.origin);
  return [Math.round(raceT * 10) / 10, +ll.lat.toFixed(6), +ll.lon.toFixed(6), Math.round(o.y * 10) / 10, Math.round(me.stats.dist * 10) / 10,
    Math.round(clamp(me.v, 0, 40) * 100) / 100, Math.round(clamp(inp.P || 0, 0, 3000)), Math.round(clamp(inp.cad || 0, 0, 250)), Math.round(clamp(inp.hr || 0, 0, 260))];
}
/* ---- выполнение плана во время заезда ---- */
// A step of the own plan is { f, r, cad, min }: a gear and a cadence. A step of a workout from intervals.icu
// (issue #471) is { w, w2, cad, min }: the power in watts at its start and at its end (a ramp moves between
// them; none for a free ride) and the cadence it asks for, if any. Cues are { at_s, text } from the start.
const Work = {
  active: false, steps: [], ends: [], idx: -1, t: 0, ss: [], warned: false, cues: [], cue: 0, name: null,
  start(steps, cues, name) {
    this.steps = steps.map(s => Object.assign({}, s)); let acc = 0; this.ends = this.steps.map(s => (acc += s.min * 60));
    this.ss = this.steps.map(() => ({ time: 0, sumCad: 0, n: 0, zone: 0, aimed: 0, sumP: 0 })); this.idx = -1; this.t = 0; this.active = true; this.warned = false;
    this.cues = cues || []; this.cue = 0; this.name = name ?? null;
  },
  total() { return this.ends[this.ends.length - 1] || 0; },
  cur() { return this.steps[Math.max(0, this.idx)]; },
  // the power the step under way asks for at this second, in watts, or null for a step without one
  target() {
    const i = Math.max(0, this.idx), s = this.steps[i]; if (!this.active || !s || s.w == null) return null;
    const from = i ? this.ends[i - 1] : 0, f = clamp((this.t - from) / (this.ends[i] - from), 0, 1);
    return Math.round(s.w + ((s.w2 == null ? s.w : s.w2) - s.w) * f);
  },
  update(dt, cad, mode, P) {
    this.t += dt;
    let i = this.ends.findIndex(e => this.t < e); if (i < 0) { this.active = false; return true; }
    if (i !== this.idx) {
      this.idx = i; this.warned = false; const s = this.steps[i], shift = s.f != null && (mode === 'cadence' || mode === 'demo');
      if (shift) { gearF = s.f; gearR = s.r; }
      rideEvent('planStep', i, s, shift);
    }
    const s = this.steps[i], st = this.ss[i], w = this.target();
    st.time += dt; st.sumP += (P || 0) * dt; if (cad > 0) { st.sumCad += cad * dt; st.n += dt; }
    // the time on the step's target: the power within 5 % of it, or else the cadence within 5 rpm of it
    if (w != null) { st.aimed += dt; if (Math.abs((P || 0) - w) <= w * .05) st.zone += dt; }
    else if (s.cad) { st.aimed += dt; if (Math.abs((cad || 0) - s.cad) <= 5) st.zone += dt; }
    while (this.cue < this.cues.length && this.cues[this.cue].at_s <= this.t) rideEvent('planCue', this.cues[this.cue++].text);
    const left = this.ends[i] - this.t, nx = this.steps[i + 1];
    if (!this.warned && left < 10 && nx) { this.warned = true; rideEvent('planSoon', nx); }
    return false;
  }
};
// A race with protocols: the rider's crossings of the start-finish line between `from` and `to` along the route --
// each lap's, the last the finish -- and of its turns (turnPoints), each told to the page with how many seconds ago
// it was, the step having gone from `from` to `to` in the last `dt` seconds
function raceCrossings(from, to, dt) {
  const rules = raceRules(); if (!rules || !rules.me || to <= from) return;
  const T = world.T, S0 = world.S0, L = T.L, found = [];
  // the line, each lap: on a loop turned back at its start, where its way back passes it (lineBack)
  const B = world.finBack || 0;
  if (T.loop) { for (let k = Math.floor((from - S0 + B) / L) + 1; S0 + k * L - B <= to; k++) if (k >= 1 && k <= rules.me.laps) found.push({ s: S0 + k * L - B, point: 0, last: k === rules.me.laps }); }
  else if (from < world.FIN && to >= world.FIN) found.push({ s: world.FIN, point: 0, last: true });
  turnPoints(T).forEach((p, i) => {
    if (!T.loop) { if (from < p && to >= p) found.push({ s: p, point: i + 1, last: false }); return; }
    for (let m = Math.floor((from - p) / L) + 1; p + m * L <= to; m++) if (p + m * L > S0 && p + m * L < world.FIN) found.push({ s: p + m * L, point: i + 1, last: false });
  });
  found.sort((a, b) => a.s - b.s).forEach(c => rideEvent('crossing', c.point, c.last, dt * (to - c.s) / (to - from)));
}
// A frame's time is ridden in steps of at most RIDE_STEP s: a device that draws few frames rides the same
// road in the same time as one that draws many. A frame longer than MAX_FRAME s is a stall (a hidden page)
// and counts as MAX_FRAME.
const RIDE_STEP = .05, MAX_FRAME = .5;
function advanceRide(dt, inp, t) { const n = Math.max(1, Math.ceil(dt / RIDE_STEP)); for (let i = 0; i < n; i++) stepRide(dt / n, inp, t); }
// one step of the ride, dt seconds at time t: the countdown, the rider, the bots and what the rider passes
const _ry = {};
function stepRide(dt, inp, t) {
  const T = world.T, grade = gradeAt(T, me.s), y0 = sampleAt(T, me.s, _ry).y;
  airAround(me, y0); // in the countdown too: a smart trainer is set to the air at the start
  if (phase === 'countdown') {
    cdT = groupRide ? (groupRide.startAt - Date.now()) / 1000 : cdT - dt; // a pause keeps no one from the start
    if (cdT <= 0) { phase = 'race'; rideEvent('go'); }
  } else if (phase === 'race' || phase === 'done') {
    if (cdT > -0.8) cdT -= dt;
    if (phase === 'race') {
      raceT += dt; const s0 = me.s, ds = inp.direct ? directStep(me, inp.wheelKmh, dt) : stepRider(me, inp.P, grade, dt); me.s += ds; me.stats.dist += ds;
      if (rideMode === 'race') raceCrossings(s0, me.s, dt);
      rideEvent('moved', s0, me.s, dt, inp); // the Strava segments the rider is on (js/segments.js)
      const st = me.stats, y1 = sampleAt(T, me.s, _ry).y; if (y1 > y0) st.gain += y1 - y0;
      st.t += dt; st.sumP += inp.P * dt; if (inp.cad > 0) { st.sumCad += inp.cad; st.nCad++; } st.maxV = Math.max(st.maxV, me.v); if (inp.mode === 'demo') st.demoT += dt; me.pAcc += inp.P * dt; me.pT += dt; if (me.pT >= 1) { me.powerLog.push(me.pAcc / me.pT); me.pAcc = 0; me.pT = 0; if (me.track.length < MAX_TRACK) me.track.push(trackPoint(inp)); } keepRR(me, inp.rr); if (inp.mode === 'power') st.real = true; if (inp.hr) { st.sumHR += inp.hr; st.nHR++; st.maxHR = Math.max(st.maxHR, inp.hr); }
      if (rideMode === 'plan' || rideMode === 'free') {
        // тренировка по плану: маршрут крутится кругами, финиш — когда закончится последний шаг; a free ride laps a
        // loop only: on a route from one place to another it ends at the finish, saved as when its rider ends it
        if (rideMode === 'free' && !T.loop && me.s >= world.FIN) rideEvent('routeEnd');
        else if (rideMode === 'plan' && !T.loop && me.s >= T.L - 15) { me.s = world.S0; rideEvent('backToStart'); }
        // laps: a loop's, or a workout's brought back to its start; a free ride from one place to another has none
        const lap = Math.floor(me.stats.dist / (world.FIN - world.S0));
        if (lap > me.lap && (T.loop || rideMode === 'plan')) { me.lap = lap; world.lms.forEach(l => { l.done = false; }); rideEvent('lap', lap + 1); }
        if (rideMode === 'plan' && Work.active && Work.update(dt, inp.cad, inp.mode, inp.P)) rideEvent('planDone');
      } else if (me.s >= world.FIN) { me.finishT = raceT; rideEvent('finish'); }
      else if (T.loop && world.FIN - world.S0 > T.L * 1.5) { // a race of several laps: each one said, at its line
        const lap = Math.floor((me.s - world.S0 + (world.finBack || 0)) / T.L);
        if (lap > me.lap) { me.lap = lap; world.lms.forEach(l => { l.done = false; }); rideEvent('lap', lap + 1); }
      }
      world.lms.forEach(l => { if (l.done || l.dist > 700) return; let past = me.s - sightCue(T, l); if (T.loop) past = ((past % T.L) + T.L) % T.L; if (past >= 0 && past < SIGHT_CUE_SPAN_M) { l.done = true; rideEvent('sight', l); } });
    } else { me.s += stepRider(me, 60, grade, dt); }
  }
  bots.forEach(b => {
    if (b.remote) { mpStepRemote(b, dt); return; }
    if (phase === 'countdown') return;
    const gb = gradeAt(T, b.s), P = botPower(b, gb, world.FIN - b.s, t);
    b.P = P;
    b.cad = botCadence(b, gb, t);
    airAround(b, sampleAt(T, b.s, _ry).y);
    b.s += stepRider(b, P, gb, dt);
    if (b.finishT == null && b.s >= world.FIN) b.finishT = raceT;
    if (!T.loop && b.s > T.L - 2) b.s = T.L - 2;
  });
  if (!T.loop && me.s > T.L - 1) me.s = T.L - 1;
}
