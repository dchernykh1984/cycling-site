'use strict';
/* ---------------- Трасса: карта, профиль, уклон, старт, финиш и ориентиры ---------------- */
// back from metres on the scene to the map: where the rider is, for the track a Strava upload carries
function unproj(x, z, O) { const R = 6371000; return { lat: O.lat - z / R * 180 / Math.PI, lon: O.lon + x / (R * Math.cos(O.lat * Math.PI / 180)) * 180 / Math.PI }; }
function proj(lat, lon, O) { const R = 6371000; return { x: (lon - O.lon) * Math.PI / 180 * R * Math.cos(O.lat * Math.PI / 180), z: -(lat - O.lat) * Math.PI / 180 * R }; }

function buildTrack(r) {
  const src = r.osm ? r.osm.path : r.pts; // если загружен файл OSM — точная ось настоящих улиц
  const O = mapOf(r).origin; // the route's metres are its map's, so its sights and riders share them
  const v = src.map(p => { const q = proj(p[0], p[1], O); return new THREE.Vector3(q.x, p[2], q.z); });
  const curve = new THREE.CatmullRomCurve3(v, !!r.loop, 'centripetal', .5);
  const n = Math.max(80, Math.round(curve.getLength() / 4));
  const sp = curve.getSpacedPoints(n);
  const N = sp.length, X = new Float32Array(N), Y0 = new Float32Array(N), Z = new Float32Array(N), Y = new Float32Array(N), D = new Float64Array(N);
  for (let i = 0; i < N; i++) { X[i] = sp[i].x; Y0[i] = sp[i].y; Z[i] = sp[i].z; }
  const R = 10, M = N - 1;
  for (let i = 0; i < N; i++) { let s = 0, c = 0; for (let k = -R; k <= R; k++) { let j = i + k; j = r.loop ? ((j % M) + M) % M : clamp(j, 0, N - 1); s += Y0[j]; c++; } Y[i] = s / c; }
  if (r.loop) Y[N - 1] = Y[0];
  for (let i = 1; i < N; i++) D[i] = D[i - 1] + Math.hypot(X[i] - X[i - 1], Z[i] - Z[i - 1]);
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
  return { route: r, origin: O, N, X, Y, Z, D, L, loop: !!r.loop, gain, minY, maxY, minX, maxX, minZ, maxZ, C, again, over };
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
function sampleAt(T, s, o) {
  if (T.loop) s = ((s % T.L) + T.L) % T.L; else s = clamp(s, 0, T.L);
  let lo = 0, hi = T.N - 1;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (T.D[m] <= s) lo = m; else hi = m; }
  const f = (s - T.D[lo]) / ((T.D[hi] - T.D[lo]) || 1);
  o.x = T.X[lo] + (T.X[hi] - T.X[lo]) * f; o.y = T.Y[lo] + (T.Y[hi] - T.Y[lo]) * f; o.z = T.Z[lo] + (T.Z[hi] - T.Z[lo]) * f;
  let tx = T.X[hi] - T.X[lo], tz = T.Z[hi] - T.Z[lo]; const l = Math.hypot(tx, tz) || 1; o.tx = tx / l; o.tz = tz / l;
  o.rx = -o.tz; o.rz = o.tx; // вправо по ходу
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
// where a rider is on the map: the route's point at their distance, moved sideways to their lane
function riderPos(R, out) { const o = sampleAt(world.T, R.s, out); o.px = o.x + o.rx * R.lane; o.pz = o.z + o.rz * R.lane; return o; }
function nearLandmarks(T) {
  const out = [];
  LANDMARKS.filter(lm => lm.city === T.route.city).forEach(lm => { // a map's own sights: two maps may show one each
    const q = proj(lm.lat, lm.lon, T.origin); let best = 1e18, bi = 0;
    for (let i = 0; i < T.N; i += 2) { const dx = T.X[i] - q.x, dz = T.Z[i] - q.z, d = dx * dx + dz * dz; if (d < best) { best = d; bi = i; } }
    const dist = Math.sqrt(best); if (dist > (lm.far ? 14000 : 1300)) return;
    const o = sampleAt(T, T.D[bi], {}), side = ((q.x - o.x) * o.rx + (q.z - o.z) * o.rz) > 0 ? 'right' : 'left';
    out.push(Object.assign({}, lm, { x: q.x, z: q.z, s: T.D[bi], side, dist }));
  });
  return out;
}
// the course of a ride: its track, where it starts and finishes, and the sights along it
// a route out and back ends where it starts: its finish is the start's line, under the one arch of both
function buildCourse(route) {
  const T = buildTrack(route), S0 = 20, back = !T.loop && Math.hypot(T.X[T.N - 1] - T.X[0], T.Z[T.N - 1] - T.Z[0]) < route.width;
  return { T, S0, FIN: T.loop ? S0 + T.L : back ? T.L - S0 : T.L - 8, back, route, lms: nearLandmarks(T) };
}
