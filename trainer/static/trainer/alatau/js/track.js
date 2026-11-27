'use strict';
/* ---------------- Трасса: карта, профиль, уклон, старт, финиш и ориентиры ---------------- */
// back from metres on the scene to the map: where the rider is, for the track a Strava upload carries
function unproj(x, z, O) { const R = 6371000; return { lat: O.lat - z / R * 180 / Math.PI, lon: O.lon + x / (R * Math.cos(O.lat * Math.PI / 180)) * 180 / Math.PI }; }
function proj(lat, lon, O) { const R = 6371000; return { x: (lon - O.lon) * Math.PI / 180 * R * Math.cos(O.lat * Math.PI / 180), z: -(lat - O.lat) * Math.PI / 180 * R }; }

function buildTrack(r) {
  const src = r.osm ? r.osm.path : r.pts; // если загружен файл OSM — точная ось настоящих улиц
  const O = r.origin || mapOf(r).origin; // the route's metres: its own origin's, else its map's; its sights and riders share them
  const v = src.map(p => { const q = proj(p[0], p[1], O); return new THREE.Vector3(q.x, p[2], q.z); });
  const curve = new THREE.CatmullRomCurve3(v, !!r.loop, 'centripetal', .5);
  // the curve measured every half metre: with three.js's 200 steps for the whole route its points came centimetres to
  // twenty metres apart, and the grade and the road bent at them
  let chord = 0; for (let i = 1; i < v.length; i++) chord += v[i].distanceTo(v[i - 1]);
  curve.arcLengthDivisions = Math.ceil(chord * 2);
  const n = Math.max(80, Math.round(curve.getLength() / 4));
  const sp = curve.getSpacedPoints(n);
  const N = sp.length, X = new Float32Array(N), Y0 = new Float32Array(N), Z = new Float32Array(N), Y = new Float32Array(N), D = new Float64Array(N);
  for (let i = 0; i < N; i++) { X[i] = sp[i].x; Y0[i] = sp[i].y; Z[i] = sp[i].z; }
  // heights averaged three times over 60 m (15 points): the grade rises and falls without a step at either end
  const R = 7, M = N - 1, at = j => r.loop ? ((j % M) + M) % M : clamp(j, 0, N - 1);
  const box = (A, B) => { for (let i = 0; i < N; i++) { let s = 0; for (let k = -R; k <= R; k++) s += A[at(i + k)]; B[i] = s / (2 * R + 1); } };
  const Y1 = new Float32Array(N); box(Y0, Y); box(Y, Y1); box(Y1, Y);
  if (r.loop) Y[N - 1] = Y[0];
  for (let i = 1; i < N; i++) D[i] = D[i - 1] + Math.hypot(X[i] - X[i - 1], Z[i] - Z[i - 1]);
  // the way the route runs at each point, from the point before it to the point after (sampleAt bends by them)
  const TX = new Float32Array(N), TZ = new Float32Array(N);
  for (let i = 0; i < N; i++) {
    const a = r.loop ? at(i - 1) : Math.max(i - 1, 0), b = r.loop ? at(i + 1) : Math.min(i + 1, N - 1);
    const dx = X[b] - X[a], dz = Z[b] - Z[a], l = Math.hypot(dx, dz) || 1; TX[i] = dx / l; TZ[i] = dz / l;
  }
  let gain = 0, minY = 1e9, maxY = -1e9, minX = 1e9, maxX = -1e9, minZ = 1e9, maxZ = -1e9;
  for (let i = 0; i < N; i++) { if (i && Y[i] > Y[i - 1]) gain += Y[i] - Y[i - 1]; minY = Math.min(minY, Y[i]); maxY = Math.max(maxY, Y[i]); minX = Math.min(minX, X[i]); maxX = Math.max(maxX, X[i]); minZ = Math.min(minZ, Z[i]); maxZ = Math.max(maxZ, Z[i]); }
  const cx = [], cz = [], cy = [], cd = [];
  for (let i = 0; i < N; i += 8) { cx.push(X[i]); cz.push(Z[i]); cy.push(Y[i]); cd.push(D[i]); }
  if (r.extend && !r.loop) { // продолжение долины за финишем (только для рельефа)
    let px = X[N - 1], pz = Z[N - 1], py = Y[N - 1], pd = D[N - 1];
    r.extend.forEach(e => { const q = proj(e[0], e[1], O), len = Math.hypot(q.x - px, q.z - pz), n = Math.max(1, Math.round(len / 30));
      for (let k = 1; k <= n; k++) { const f = k / n; cx.push(px + (q.x - px) * f); cz.push(pz + (q.z - pz) * f); cy.push(py + (e[2] - py) * f); cd.push(pd + len * f); }
      px = q.x; pz = q.z; py = e[2]; pd += len; });
  }
  const C = { x: Float32Array.from(cx), z: Float32Array.from(cz), y: Float32Array.from(cy), d: Float32Array.from(cd) };
  const L = D[N - 1], { again, over } = ridden(X, Z, D, L, !!r.loop, r.width || 8);
  // where each of the route's points lies along it: its bridges and tunnels are stretches between two of them. The
  // first time the route passes it: one that passes a place again later -- a loop turned back at its start comes back
  // onto its first point -- put the points of that turn at its very end, and their rider's line with them
  const ptS = new Float64Array(v.length), PASSED = 9; // within 3 m: the curve runs through every point, 4 m a sample
  for (let k = 0, j = 0; k < v.length; k++) {
    let best = Infinity, bj = j;
    for (let m = j; m < Math.min(N, j + 600); m++) {
      const d = (X[m] - v[k].x) ** 2 + (Z[m] - v[k].z) ** 2;
      if (d < best) { best = d; bj = m; } else if (best < PASSED) break;
    }
    ptS[k] = D[bj]; j = bj;
  }
  // a point's fourth value is the rider's line: metres right of the road's middle, the source track's way through
  // a corner it took by the apex (js/maps.js)
  let line = null;
  if (!r.osm && src.every(p => p.length > 3)) {
    line = new Float32Array(N);
    for (let i = 0, k = 0; i < N; i++) {
      while (k + 1 < src.length && ptS[k + 1] <= D[i]) k++;
      const k2 = k + 1 < src.length ? k + 1 : (r.loop ? 0 : k), s1 = k2 > k ? ptS[k2] : L, f = s1 > ptS[k] ? clamp((D[i] - ptS[k]) / (s1 - ptS[k]), 0, 1) : 0;
      line[i] = src[k][3] + (src[k2][3] - src[k][3]) * f;
    }
  }
  // the streets it rides, each from the point where it begins (maps.js): { s, n: its names, null where none }
  const streets = (r.streets || []).map(([k, nm]) => ({ s: ptS[k] || 0, n: nm }));
  const T = { route: r, origin: O, N, X, Y, Z, D, L, TX, TZ, streets, loop: !!r.loop, gain, minY, maxY, minX, maxX, minZ, maxZ, C, again, over, ptS, line };
  T.half = narrowHalves(T, r);
  return T;
}
// Where a route comes back onto road it rode before -- out and back along one road, a loop round a turn: again[i]
// is 1 where point i lies on the road of a stretch ridden earlier (its own lane apart), over[i] how many earlier
// stretches its road overlaps. A stretch is earlier when it is more than two road widths behind along the route.
function segDist(px, pz, ax, az, bx, bz) {
  const dx = bx - ax, dz = bz - az, f = clamp(((px - ax) * dx + (pz - az) * dz) / (dx * dx + dz * dz || 1), 0, 1);
  return Math.hypot(px - ax - dx * f, pz - az - dz * f);
}
function ridden(X, Z, D, L, loop, W) {
  const N = X.length, again = new Uint8Array(N), over = new Uint8Array(N), cell = new Map(), gap = 2 * W + 20;
  const key = (x, z) => Math.floor(x / W) + ',' + Math.floor(z / W);
  for (let i = 0; i < N; i++) {
    const near = [];
    for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) {
      for (const j of cell.get((Math.floor(X[i] / W) + a) + ',' + (Math.floor(Z[i] / W) + b)) || []) {
        const back = D[i] - D[j];
        if (back > gap && (!loop || L - back > gap) && Math.hypot(X[i] - X[j], Z[i] - Z[j]) < W) near.push(j);
      }
    }
    if (near.some(j => j + 1 < N && segDist(X[i], Z[i], X[j], Z[j], X[j + 1], Z[j + 1]) < 1.5)) again[i] = 1; // points 4 m apart
    near.sort((a, b) => D[a] - D[b]);
    for (let k = 0; k < near.length; k++) if (!k || D[near[k]] - D[near[k - 1]] > gap) over[i]++;
    const c = key(X[i], Z[i]); if (!cell.has(c)) cell.set(c, []); cell.get(c).push(i);
  }
  return { again, over };
}
// A stretch on a narrower road than the route's (narrow.py's "narrow", [[point, point, width, lanes]] -- Granfondo
// 2026's frontage roads and their crossing over Al-Farabi at its near turn): the road's half width at each sample,
// eased over NARROW_EASE_M at each end, and its lanes (T.halfLanes); null for a route with none
const NARROW_EASE_M = 20;
function narrowHalves(T, r) {
  if (!r.narrow) return null;
  const out = new Float32Array(T.N).fill(r.width / 2);
  T.halfLanes = new Uint8Array(T.N).fill(r.lanes);
  r.narrow.forEach(([i0, i1, w, lanes]) => {
    const s0 = T.ptS[i0], s1 = T.ptS[i1];
    for (let i = 0; i < T.N; i++) {
      const s = T.D[i], k = s < s0 ? (s0 - s) / NARROW_EASE_M : s > s1 ? (s - s1) / NARROW_EASE_M : 0, h = w / 2 + (r.width - w) / 2 * k * k * (3 - 2 * k);
      if (k < 1 && h < out[i]) { out[i] = h; T.halfLanes[i] = lanes; }
    }
  });
  return out;
}
// the road's half width where a rider is
function halfAt(T, s) {
  if (!T.half) return T.route.width / 2;
  if (T.loop) s = ((s % T.L) + T.L) % T.L;
  return T.half[clamp(Math.round(s / (T.L / (T.N - 1))), 0, T.N - 1)];
}
function sampleAt(T, s, o) {
  if (T.loop) s = ((s % T.L) + T.L) % T.L; else s = clamp(s, 0, T.L);
  let lo = 0, hi = T.N - 1;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (T.D[m] <= s) lo = m; else hi = m; }
  const f = (s - T.D[lo]) / ((T.D[hi] - T.D[lo]) || 1);
  // between two points the route bends as their ways say, a cubic from one to the other: a corner turns smoothly,
  // where a straight line between them turned at each point and a lane's line jumped back there by up to two metres
  const d = T.D[hi] - T.D[lo], f2 = f * f, f3 = f2 * f, a0 = 2 * f3 - 3 * f2 + 1, a1 = (f3 - 2 * f2 + f) * d, b0 = 3 * f2 - 2 * f3, b1 = (f3 - f2) * d;
  o.x = a0 * T.X[lo] + a1 * T.TX[lo] + b0 * T.X[hi] + b1 * T.TX[hi]; o.z = a0 * T.Z[lo] + a1 * T.TZ[lo] + b0 * T.Z[hi] + b1 * T.TZ[hi];
  o.y = T.Y[lo] + (T.Y[hi] - T.Y[lo]) * f;
  const g0 = 6 * f2 - 6 * f, g1 = (3 * f2 - 4 * f + 1) * d, g2 = (3 * f2 - 2 * f) * d;
  const tx = g0 * (T.X[lo] - T.X[hi]) + g1 * T.TX[lo] + g2 * T.TX[hi], tz = g0 * (T.Z[lo] - T.Z[hi]) + g1 * T.TZ[lo] + g2 * T.TZ[hi], l = Math.hypot(tx, tz) || 1;
  o.tx = tx / l; o.tz = tz / l;
  o.rx = -o.tz; o.rz = o.tx; // вправо по ходу
  o.line = T.line ? T.line[lo] + (T.line[hi] - T.line[lo]) * f : null;
  return o;
}
const _ga = {}, _gb = {};
function gradeAt(T, s) {
  let a = s - 15, b = s + 15;
  if (!T.loop) { a = clamp(a, 0, T.L); b = clamp(b, 0, T.L); }
  const d = b - a; if (d < 1) return 0;
  return (sampleAt(T, b, _gb).y - sampleAt(T, a, _ga).y) / d;
}
function nearest(T, x, z) {
  const C = T.C; let best = 1e18, bi = 0;
  for (let i = 0; i < C.x.length; i++) { const dx = C.x[i] - x, dz = C.z[i] - z, d = dx * dx + dz * dz; if (d < best) { best = d; bi = i; } }
  return { d: Math.sqrt(best), y: C.y[bi], s: C.d[bi] };
}
// how far a point is from the route itself: nearest() measures to its coarse points, 32 m apart along it, which
// puts a point on the road up to 16 m away. Within ROUTE_CELL of the route the route's own points say it exactly (a
// grid of them, laid once per track); further out the coarse measure is near enough.
const ROUTE_CELL = 16;
function routeGap(T, x, z) {
  if (!T.grid) {
    T.grid = new Map();
    for (let i = 0; i < T.N; i++) { const k = Math.floor(T.X[i] / ROUTE_CELL) + ',' + Math.floor(T.Z[i] / ROUTE_CELL); if (!T.grid.has(k)) T.grid.set(k, []); T.grid.get(k).push(i); }
  }
  const cx = Math.floor(x / ROUTE_CELL), cz = Math.floor(z / ROUTE_CELL); let best = Infinity;
  for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) for (const i of T.grid.get((cx + a) + ',' + (cz + b)) || []) best = Math.min(best, Math.hypot(T.X[i] - x, T.Z[i] - z));
  return best <= ROUTE_CELL ? best : Math.min(best, nearest(T, x, z).d);
}
// the route's nearest point to (x, z) as routeGap finds it: { d: how far, y: its height, s: where along the route }
function routeNearest(T, x, z) {
  if (!T.grid) routeGap(T, x, z);
  const cx = Math.floor(x / ROUTE_CELL), cz = Math.floor(z / ROUTE_CELL); let best = Infinity, bi = -1;
  for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) for (const i of T.grid.get((cx + a) + ',' + (cz + b)) || []) { const d = Math.hypot(T.X[i] - x, T.Z[i] - z); if (d < best) { best = d; bi = i; } }
  if (best <= ROUTE_CELL) return { d: best, y: T.Y[bi], s: T.D[bi] };
  const n = nearest(T, x, z); return { d: Math.min(best, n.d), y: n.y, s: n.s };
}
// the names of the street the route rides at distance s, or null where the map has none
function streetAt(T, s) {
  if (T.loop) s = ((s % T.L) + T.L) % T.L;
  let at = null; for (const st of T.streets) { if (st.s > s) break; at = st.n; }
  return at;
}
// The lane a rider keeps on a road this wide: the right one, a metre and a half in from the edge
const keepLane = W => Math.min(3.2, W / 2 - 1.5);
// how far right of the road's middle a rider rides at the place o (a sample of the track): their lane; on a route
// that carries its rider's line, that line -- the apex of a corner taken by it -- with a bunch spread round it as round
// the right lane, all within the road's edges
function laneOf(R, o, s = R.s) {
  if (o.line == null) return R.lane;
  const W = world.T.route.width, h = halfAt(world.T, s || 0); // the road's width where o is, not where the rider is
  return clamp(o.line + R.lane - keepLane(W), -h + .6, h - .6);
}
// where a rider is on the map: the route's point at their distance, moved sideways to their lane
function riderPos(R, out, s = R.s) { const o = sampleAt(world.T, s, out), lane = laneOf(R, o, s); o.px = o.x + o.rx * lane; o.pz = o.z + o.rz * lane; return o; }
const _hb = {}, _hf = {};
// the way a rider faces: along the line they ride, from a metre behind them to a metre ahead -- or, where those two
// meet, past the end of a route that is not a loop (a finisher rolling on), the route's own way there
function riderHeading(R) {
  const b = riderPos(R, _hb, R.s - 1), f = riderPos(R, _hf, R.s + 1), dx = f.px - b.px, dz = f.pz - b.pz;
  return dx * dx + dz * dz > 1e-6 ? Math.atan2(dx, dz) : Math.atan2(f.tx, f.tz);
}
// The route's first pass by a place on its metres: the earliest of its points within FIRST_PASS_M of the nearest. A road
// ridden out and back passes it twice, each pass's points 4 m apart: within a metre, its way back's came first
const FIRST_PASS_M = 2.5;
function firstPassAt(T, x, z) {
  const d2 = i => (T.X[i] - x) ** 2 + (T.Z[i] - z) ** 2; let best = Infinity;
  for (let i = 0; i < T.N; i++) best = Math.min(best, d2(i));
  let i = 0; while (Math.sqrt(d2(i)) > Math.sqrt(best) + FIRST_PASS_M) i++;
  return i;
}
const SIGHT_ACROSS = .7; // a road within 45 degrees of running across the mountains' way
function nearLandmarks(T) {
  const out = [];
  LANDMARKS.filter(lm => lm.city === T.route.city).forEach(lm => { // a map's own sights: two maps may show one each
    const q = proj(lm.lat, lm.lon, T.origin); let best = 1e18, bi = 0;
    for (let i = 0; i < T.N; i += 2) { const dx = T.X[i] - q.x, dz = T.Z[i] - q.z, d = dx * dx + dz * dz; if (d < best) { best = d; bi = i; } }
    // on a road ridden there and back, the first pass: the Cosmostation's Flow Park, on the left on the way up, was
    // told on the right at the end of the lap
    for (let i = 0; i < bi; i++) if (Math.hypot(T.X[i] - q.x, T.Z[i] - q.z) <= Math.sqrt(best) + FIRST_PASS_M) { bi = i; break; }
    // a sight is shown within its reach of the route: its own, else 14 km for one seen from afar, else 1.3 km
    const dist = Math.sqrt(best); if (dist > (lm.reach || (lm.far ? 14000 : 1300))) return;
    const o = sampleAt(T, T.D[bi], {});
    const side = ((q.x - o.x) * o.rx + (q.z - o.z) * o.rz) > 0 ? 'right' : 'left';
    // one told as on the mountains' side ("told": "mountains"), where the road runs across their way and it stands
    // toward them: on Granfondo's out-and-back past Flow Park, left one way and right the other, the side it was
    // told on was not the side the rider saw it on
    const range = lm.told === 'mountains' && (T.route.mountains || mapOf(T.route).mountains);
    const said = range && range.south != null && Math.abs(o.tz) < SIGHT_ACROSS && q.z > o.z ? 'mountains' : side;
    out.push(Object.assign({}, lm, { x: q.x, z: q.z, s: T.D[bi], side, said, dist }));
  });
  return out;
}
// A route's control points beyond its start-finish line: its turns back -- the road reversing its way within 60 m
// either side, a U-turn across a dual carriageway, the loop at the end of an out-and-back -- each at its middle, where
// the way there and the way back 200 m either side come closest, as distances along the route (specs/495-virtual-race).
// Two within 120 m are one turn; a turn after which the route does not come back alongside itself -- 200 m either
// side further apart than 60 m, a circuit's hairpin -- is none.
function turnPoints(T) {
  if (T.turns) return T.turns;
  const k = 15, way = i => Math.atan2(T.Z[i + 1] - T.Z[i], T.X[i + 1] - T.X[i]), found = [], a = {}, b = {};
  for (let i = k; i + k + 1 < T.N; i++) {
    const turn = Math.abs(((way(i + k) - way(i - k) + 3 * Math.PI) % (2 * Math.PI)) - Math.PI);
    if (turn < Math.PI * .8) continue;
    sampleAt(T, T.D[i] - 200, a); sampleAt(T, T.D[i] + 200, b);
    const gap = Math.hypot(a.x - b.x, a.z - b.z), last = found[found.length - 1];
    if (last && T.D[i] - last.end < 120) { last.end = T.D[i]; if (gap < last.gap) Object.assign(last, { s: T.D[i], gap }); }
    else found.push({ s: T.D[i], end: T.D[i], gap });
  }
  T.turns = found.filter(f => f.gap < 60).map(f => f.s);
  return T.turns;
}
// Where a rider is told of a sight beside the route: SIGHT_AHEAD_M before its nearest point, earlier the further it
// stands off, so that it is ahead to one side and in view; and before a tunnel's cutting that would hide it then --
// Nurly Tau was told of in the cutting by Al-Farabi's tunnel, its walls in the way
const SIGHT_AHEAD_M = 220, SIGHT_CUE_SPAN_M = 60, SIGHT_OFF_AHEAD = 1.2;
function sightCue(T, l) {
  if (l.cue != null) return l.cue;
  let at = l.s - Math.max(SIGHT_AHEAD_M, l.dist * SIGHT_OFF_AHEAD);
  const zones = typeof tunnelZones === 'function' && T.route.tunnels ? tunnelZones(T) : [];
  for (const z of zones) if (at >= z.s0 - 20 && at <= z.s1 + 20) at = z.s0 - 40;
  l.cue = T.loop ? ((at % T.L) + T.L) % T.L : Math.max(0, at);
  return l.cue;
}
// the course of a ride: its track, where it starts and finishes, and the sights along it
// a route out and back ends where it starts: its finish is the start's line, under the one arch of both
// A loop turned back at its start (Kyrbaltabay's): its way back passes the start line heading the other way before
// that turn, and a race finishes there, as in life -- its last lap so many metres short of a whole one (race.js).
// 0 for any other loop: one that passes its line once a lap. Its way back is looked for over the loop's last
// LINE_BACK_M, half a metre at a time.
const LINE_BACK_M = 300;
function lineBack(T, S0) {
  if (!T.loop) return 0;
  const line = sampleAt(T, S0, {}), o = {};
  let best = 1, at = null;
  for (let s = T.L; s > T.L - LINE_BACK_M; s -= .5) {
    sampleAt(T, s, o);
    const d = Math.hypot(o.x - line.x, o.z - line.z);
    if (d < best && o.tx * line.tx + o.tz * line.tz < -.9) { best = d; at = s; }
  }
  return at == null ? 0 : T.L + S0 - at;
}
function buildCourse(route) {
  const T = buildTrack(route), S0 = 20, back = !T.loop && Math.hypot(T.X[T.N - 1] - T.X[0], T.Z[T.N - 1] - T.Z[0]) < route.width;
  const FIN = T.loop ? S0 + T.L : back ? T.L - S0 : T.L - 8;
  return { T, S0, FIN, FIN1: FIN, finBack: lineBack(T, S0), back, route, lms: nearLandmarks(T) };
}
