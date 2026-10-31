'use strict';
const ORIGIN = { lat: 43.238, lon: 76.945 };
// back from metres on the scene to the map: where the rider is, for the track a Strava upload carries
function unproj(x, z) { const R = 6371000; return { lat: ORIGIN.lat - z / R * 180 / Math.PI, lon: ORIGIN.lon + x / (R * Math.cos(ORIGIN.lat * Math.PI / 180)) * 180 / Math.PI }; }
function proj(lat, lon) { const R = 6371000; return { x: (lon - ORIGIN.lon) * Math.PI / 180 * R * Math.cos(ORIGIN.lat * Math.PI / 180), z: -(lat - ORIGIN.lat) * Math.PI / 180 * R }; }

function buildTrack(r) {
  const src = r.osm ? r.osm.path : r.pts; // если загружен файл OSM — точная ось настоящих улиц
  const v = src.map(p => { const q = proj(p[0], p[1]); return new THREE.Vector3(q.x, p[2], q.z); });
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
    r.extend.forEach(e => { const q = proj(e[0], e[1]), len = Math.hypot(q.x - px, q.z - pz), n = Math.max(1, Math.round(len / 30));
      for (let k = 1; k <= n; k++) { const f = k / n; cx.push(px + (q.x - px) * f); cz.push(pz + (q.z - pz) * f); cy.push(py + (e[2] - py) * f); cd.push(pd + len * f); }
      px = q.x; pz = q.z; py = e[2]; pd += len; });
  }
  const C = { x: Float32Array.from(cx), z: Float32Array.from(cz), y: Float32Array.from(cy), d: Float32Array.from(cd) };
  return { route: r, N, X, Y, Z, D, L: D[N - 1], loop: !!r.loop, gain, minY, maxY, minX, maxX, minZ, maxZ, C };
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
function terrainH(T, x, z) {
  const n = nearest(T, x, z); let h = n.y - 1.2;
  if (T.route.scenery === 'gorge') {
    if (n.d > 45) { const k = n.d - 45, f = clamp((n.s - 1200) / 3000, .12, 1); h += f * (k * .46 + fbm(x * .004, z * .004) * Math.min(1, k / 120) * 70); }
  } else if (n.d > 70) { h += (fbm(x * .003, z * .003) - .5) * 5 * Math.min(1, (n.d - 70) / 250); }
  return h;
}
