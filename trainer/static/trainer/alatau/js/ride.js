'use strict';
/* ---------------- Заезд: состояние и шаг ---------------- */
// The ride itself, apart from its drawing: nothing here reads the page or draws. Each frame the ride
// takes a step; the scene and the HUD are then drawn from its state, and what happened during the
// step reaches the page through rideHooks.
let world = null; // the course being ridden (js/track.js)
let phase = 'loading', bots = [], me = null, raceT = 0, cdT = 0;
let rideMode = 'race';  // режим текущего заезда: race | plan | free
// what the page does when something happens in the ride: go, lap, backToStart, sight, finish, planStep, planSoon, planDone
const rideHooks = {};
function rideEvent(type, ...args) { const f = rideHooks[type]; if (f) f(...args); }
function newRider(name, color, mass, s, lane) { return { name, color, mass, v: 0, s, lane, CdA: PHYS.CdA, phase: Math.random() * 6, finishT: null, P: 0 }; }
// a rider at the start of a ride: nothing ridden yet
function startRider(r) {
  r.stats = { dist: 0, gain: 0, sumP: 0, sumCad: 0, nCad: 0, maxV: 0, t: 0, sumHR: 0, nHR: 0, maxHR: 0, real: false, demoT: 0 };
  r.powerLog = []; r.pAcc = 0; r.pT = 0; r.track = []; r.lap = 0;
  return r;
}
const MAX_TRACK = 6 * 3600; // the site keeps six hours of a ride's track, a point a second
// [t_s, lat, lon, ele_m, distance_m, speed_ms, power_w, cadence_rpm, hr_bpm]: the route's place on the map, not a GPS fix
function trackPoint(inp) {
  const o = riderPos(me, {}), ll = unproj(o.px, o.pz, world.T.origin);
  return [Math.round(raceT * 10) / 10, +ll.lat.toFixed(6), +ll.lon.toFixed(6), Math.round(o.y * 10) / 10, Math.round(me.stats.dist * 10) / 10,
    Math.round(clamp(me.v, 0, 40) * 100) / 100, Math.round(clamp(inp.P || 0, 0, 3000)), Math.round(clamp(inp.cad || 0, 0, 250)), Math.round(clamp(inp.hr || 0, 0, 260))];
}
/* ---- выполнение плана во время заезда ---- */
const Work = {
  active: false, steps: [], ends: [], idx: -1, t: 0, ss: [], warned: false,
  start(steps) {
    this.steps = steps.map(s => Object.assign({}, s)); let acc = 0; this.ends = this.steps.map(s => (acc += s.min * 60));
    this.ss = this.steps.map(() => ({ time: 0, sumCad: 0, n: 0, zone: 0 })); this.idx = -1; this.t = 0; this.active = true; this.warned = false;
  },
  total() { return this.ends[this.ends.length - 1] || 0; },
  cur() { return this.steps[Math.max(0, this.idx)]; },
  update(dt, cad, mode) {
    this.t += dt;
    let i = this.ends.findIndex(e => this.t < e); if (i < 0) { this.active = false; return true; }
    if (i !== this.idx) {
      this.idx = i; this.warned = false; const s = this.steps[i], shift = mode === 'cadence' || mode === 'demo';
      if (shift) { gearF = s.f; gearR = s.r; }
      rideEvent('planStep', i, s, shift);
    }
    const s = this.steps[i], st = this.ss[i];
    st.time += dt; if (cad > 0) { st.sumCad += cad * dt; st.n += dt; } if (Math.abs((cad || 0) - s.cad) <= 5) st.zone += dt;
    const left = this.ends[i] - this.t, nx = this.steps[i + 1];
    if (!this.warned && left < 10 && nx) { this.warned = true; rideEvent('planSoon', nx); }
    return false;
  }
};
// A frame's time is ridden in steps of at most RIDE_STEP s: a device that draws few frames rides the same
// road in the same time as one that draws many. A frame longer than MAX_FRAME s is a stall (a hidden page)
// and counts as MAX_FRAME.
const RIDE_STEP = .05, MAX_FRAME = .5;
function advanceRide(dt, inp, t) { const n = Math.max(1, Math.ceil(dt / RIDE_STEP)); for (let i = 0; i < n; i++) stepRide(dt / n, inp, t); }
// one step of the ride, dt seconds at time t: the countdown, the rider, the bots and what the rider passes
const _ry = {};
function stepRide(dt, inp, t) {
  const T = world.T, grade = gradeAt(T, me.s);
  if (phase === 'countdown') {
    cdT -= dt;
    if (cdT <= 0) { phase = 'race'; rideEvent('go'); }
  } else if (phase === 'race' || phase === 'done') {
    if (cdT > -0.8) cdT -= dt;
    const y0 = sampleAt(T, me.s, _ry).y;
    if (phase === 'race') {
      raceT += dt; const ds = inp.direct ? directStep(me, inp.wheelKmh, dt) : stepRider(me, inp.P, grade, dt); me.s += ds; me.stats.dist += ds;
      const st = me.stats, y1 = sampleAt(T, me.s, _ry).y; if (y1 > y0) st.gain += y1 - y0;
      st.t += dt; st.sumP += inp.P * dt; if (inp.cad > 0) { st.sumCad += inp.cad; st.nCad++; } st.maxV = Math.max(st.maxV, me.v); if (inp.mode === 'demo') st.demoT += dt; me.pAcc += inp.P * dt; me.pT += dt; if (me.pT >= 1) { me.powerLog.push(me.pAcc / me.pT); me.pAcc = 0; me.pT = 0; if (me.track.length < MAX_TRACK) me.track.push(trackPoint(inp)); } if (inp.mode === 'power') st.real = true; if (inp.hr) { st.sumHR += inp.hr; st.nHR++; st.maxHR = Math.max(st.maxHR, inp.hr); }
      if (rideMode === 'plan' || rideMode === 'free') {
        // тренировка по плану: маршрут крутится кругами, финиш — когда закончится последний шаг
        if (!T.loop && me.s >= T.L - 15) { me.s = world.S0; rideEvent('backToStart'); }
        const lap = Math.floor(me.stats.dist / (world.FIN - world.S0));
        if (lap > me.lap) { me.lap = lap; world.lms.forEach(l => { l.done = false; }); rideEvent('lap', lap + 1); }
        if (rideMode === 'plan' && Work.update(dt, inp.cad, inp.mode)) rideEvent('planDone');
      } else if (me.s >= world.FIN) { me.finishT = raceT; rideEvent('finish'); }
      world.lms.forEach(l => { if (l.done || l.dist > 700) return; let ahead = l.s - me.s; if (T.loop) ahead = ((ahead % T.L) + T.L) % T.L; if (ahead < 220 && ahead > -40) { l.done = true; rideEvent('sight', l); } });
    } else { me.s += stepRider(me, 60, grade, dt); }
  }
  bots.forEach(b => {
    if (b.remote) { mpStepRemote(b, dt); return; }
    if (phase === 'countdown') return;
    const gb = gradeAt(T, b.s), P = botPower(b, gb, world.FIN - b.s, t);
    b.P = P;
    b.cad = botCadence(b, gb, t);
    b.s += stepRider(b, P, gb, dt);
    if (b.finishT == null && b.s >= world.FIN) b.finishT = raceT;
    if (!T.loop && b.s > T.L - 2) b.s = T.L - 2;
  });
  if (!T.loop && me.s > T.L - 1) me.s = T.L - 1;
}
