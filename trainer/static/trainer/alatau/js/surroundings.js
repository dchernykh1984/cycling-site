'use strict';
/* ---------------- What stands round a route: its roads, bridges and tunnels, lines and water ---------------- */
// Each from a route's own data (js/maps.js), in latitude and longitude, as OpenStreetMap maps it; drawn into the
// scenery's group G of the track T, a road W metres wide, on the ground as drawn (ground(x, z)).
const xzOf = (T, p) => proj(p[0], p[1], T.origin);
// a line of points every `step` metres along a polyline of { x, z }
function along(q, step) {
  const out = [];
  for (let i = 0; i + 1 < q.length; i++) {
    const a = q[i], b = q[i + 1], L = Math.hypot(b.x - a.x, b.z - a.z), n = Math.max(1, Math.ceil(L / step));
    for (let j = 0; j < n; j++) out.push({ x: a.x + (b.x - a.x) * j / n, z: a.z + (b.z - a.z) * j / n });
  }
  if (q.length) out.push(q[q.length - 1]);
  return out;
}
// a band of half-width h -- a number, or one per point from h(point) -- along points, each of its edges' points at the
// height y gives that point (and its index), its geometry's positions and indexes added to P and I
function band(P, I, pts, h, y) {
  const base = P.length / 3;
  pts.forEach((p, i) => {
    const a = pts[Math.max(0, i - 1)], b = pts[Math.min(pts.length - 1, i + 1)], L = Math.hypot(b.x - a.x, b.z - a.z) || 1, w = typeof h === 'function' ? h(p) : h;
    const rx = -(b.z - a.z) / L, rz = (b.x - a.x) / L, l = { x: p.x - rx * w, z: p.z - rz * w }, r = { x: p.x + rx * w, z: p.z + rz * w };
    P.push(l.x, y(l, i), l.z, r.x, y(r, i), r.z);
    if (i) { const v = base + i * 2; I.push(v - 2, v - 1, v, v - 1, v + 1, v); }
  });
}
function meshOf(G, P, I, mat, name) {
  if (!I.length) return null;
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(P, 3)); g.setIndex(I); g.computeVertexNormals();
  const m = new THREE.Mesh(g, mat); m.name = name; G.add(m); return m;
}
// a wall standing on a line of { x, z, y0, y1 } points, thick metres through: two faces and its top
function wallOf(P, I, pts, thick) {
  for (let i = 0; i + 1 < pts.length; i++) {
    const a = pts[i], b = pts[i + 1], L = Math.hypot(b.x - a.x, b.z - a.z) || 1, nx = -(b.z - a.z) / L * thick / 2, nz = (b.x - a.x) / L * thick / 2;
    for (const k of [-1, 1]) {
      const v = P.length / 3;
      P.push(a.x + nx * k, a.y0, a.z + nz * k, b.x + nx * k, b.y0, b.z + nz * k, b.x + nx * k, b.y1, b.z + nz * k, a.x + nx * k, a.y1, a.z + nz * k);
      I.push(v, v + 1, v + 2, v, v + 2, v + 3);
    }
    const v = P.length / 3;
    P.push(a.x - nx, a.y1, a.z - nz, b.x - nx, b.y1, b.z - nz, b.x + nx, b.y1, b.z + nz, a.x + nx, a.y1, a.z + nz);
    I.push(v, v + 1, v + 2, v, v + 2, v + 3);
  }
}

// --- the route's own tunnels: [ramp's start, portal, portal, ramp's end] as indexes of its points. The road goes
// down between the ramps; the land beside it keeps the line between the ramps' ends, the ground the tunnel is cut in.
function tunnelZones(T) {
  if (T.zones) return T.zones;
  T.zones = (T.route.tunnels || []).map(([r0, i0, i1, r1]) => ({
    s0: T.ptS[r0], s1: T.ptS[r1], p0: T.ptS[i0], p1: T.ptS[i1], y0: T.route.pts[r0][2], y1: T.route.pts[r1][2]
  }));
  return T.zones;
}
// the ground line over a tunnel's ramps and the tunnel at s along the route, or null
function cutGround(T, s, pad = 0) {
  for (const z of tunnelZones(T)) if (s >= z.s0 - pad && s <= z.s1 + pad) return z.y0 + (z.y1 - z.y0) * clamp((s - z.s0) / (z.s1 - z.s0 || 1), 0, 1);
  return null;
}
// over a tunnel itself, the street that crosses it: the ground line, not the road below
function overTunnel(T, s) {
  for (const z of tunnelZones(T)) if (s >= z.p0 - 6 && s <= z.p1 + 6) return z.y0 + (z.y1 - z.y0) * clamp((s - z.s0) / (z.s1 - z.s0 || 1), 0, 1);
  return null;
}

// The land is drawn in cells 40 m across: over a tunnel and its cutting it would span the road like a lid, and a cell
// sloping down to the road would cut through the tunnel. So inside their walls, below a little over the ground line,
// the land's shader leaves it out: the zone as boxes along the route, 50 m long at most, wide enough for the bend.
function holesOf(T, W) {
  const out = [], a = {}, b = {}, m = {};
  tunnelZones(T).forEach(z => {
    const n = Math.max(1, Math.ceil((z.s1 - z.s0) / 50));
    for (let k = 0; k < n; k++) {
      const sa = z.s0 + (z.s1 - z.s0) * k / n, sb = z.s0 + (z.s1 - z.s0) * (k + 1) / n;
      sampleAt(T, sa, a); sampleAt(T, sb, b);
      const L = Math.hypot(b.x - a.x, b.z - a.z) || 1, ux = (b.x - a.x) / L, uz = (b.z - a.z) / L;
      let bend = 0;
      for (let s = sa; s <= sb; s += 5) { sampleAt(T, s, m); bend = Math.max(bend, Math.abs((m.z - a.z) * ux - (m.x - a.x) * uz)); }
      out.push([new THREE.Vector4((a.x + b.x) / 2, (a.z + b.z) / 2, ux, uz), new THREE.Vector4(L / 2 + .5, W / 2 + .35 + bend, cutGround(T, sa), cutGround(T, sb))]);
    }
  });
  return out;
}
function landMaterial(T, W) {
  const mat = new THREE.MeshLambertMaterial({ vertexColors: true }), holes = holesOf(T, W), n = holes.length;
  if (!n) return mat;
  mat.customProgramCacheKey = () => 'land-holes-' + n; // the shader's arrays are as long as the route's boxes
  mat.onBeforeCompile = sh => {
    sh.uniforms.holeA = { value: holes.map(h => h[0]) }; sh.uniforms.holeB = { value: holes.map(h => h[1]) };
    sh.vertexShader = 'varying vec3 vHoleW;\n' + sh.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\n  vHoleW = (modelMatrix * vec4(transformed, 1.0)).xyz;');
    sh.fragmentShader = 'uniform vec4 holeA[' + n + '];\nuniform vec4 holeB[' + n + '];\nvarying vec3 vHoleW;\n' + sh.fragmentShader.replace('void main() {', `void main() {
  for (int i = 0; i < ${n}; i++) {
    vec2 d = vHoleW.xz - holeA[i].xy;
    float u = dot(d, holeA[i].zw), v = dot(d, vec2(-holeA[i].w, holeA[i].z));
    if (abs(u) < holeB[i].x && abs(v) < holeB[i].y && vHoleW.y < mix(holeB[i].z, holeB[i].w, clamp(u / (2.0 * holeB[i].x) + 0.5, 0.0, 1.0)) + 1.5) discard;
  }`);
  };
  return mat;
}

const ROAD_CREASE_M = 2.5, ROAD_JOIN_M = 1, RAMP_WALL_GAP_M = .3, ROAD_NARROWEST_HALF_M = 1;
// --- the roads round the route: on the ground, rising onto the route's own road where they meet it
function addRoads(G, T, W, roads, ground, decks = []) {
  const P = [], I = [], WP = [], WI = [], ramps = rampsOf(T, roads, decks, ground);
  // a deck's end, where a road onto a bridge begins: not a place where the road runs into the route's own
  const deckEnds = decks.filter(d => !d.b.foot).flatMap(d => [d.q[0], d.q[d.q.length - 1]]);
  const atDeck = p => deckEnds.some(e => Math.hypot(e.x - p.x, e.z - p.z) < TOUCH_M);
  roads.forEach((r, k) => {
    const lift = .02 + (k % 5) * .015, q = along(r.pts.map(p => xzOf(T, p)), 5), up = ramps[k]; // two roads that meet never flicker
    // a slip road that runs into the route's own road comes down to it over its last 30 m, from a ramp too; a ramp
    // elsewhere keeps its height, beside the route's edge as well -- a deck's end may stand a metre off it
    const joins = [q[0], q[q.length - 1]].map(p => routeNearest(T, p.x, p.z).d < W / 2 + 3 && !atDeck(p));
    const cum = [0];
    for (let i = 1; i < q.length; i++) cum.push(cum[i - 1] + Math.hypot(q[i].x - q[i - 1].x, q[i].z - q[i - 1].z));
    const toJoin = i => Math.min(joins[0] ? cum[i] : Infinity, joins[1] ? cum[cum.length - 1] - cum[i] : Infinity);
    // the land under a point of the road and ROAD_CREASE_M either way along it: a stretch between two points crossing
    // a fold of the land drawn -- its planes tens of metres wide -- went under it, by up to 6 m on Medeu's slopes
    const onLand = (p, i) => {
      const a = q[Math.max(0, i - 1)], b = q[Math.min(q.length - 1, i + 1)], L = Math.hypot(b.x - a.x, b.z - a.z) || 1;
      const dx = (b.x - a.x) / L * ROAD_CREASE_M, dz = (b.z - a.z) / L * ROAD_CREASE_M;
      return Math.max(...[-1, -.5, 0, .5, 1].map(k => ground(p.x + dx * k, p.z + dz * k)));
    };
    const height = (p, i) => {
      const n = routeNearest(T, p.x, p.z), land = onLand(p, i) + lift, g = Math.max(land, up ? up[i] : -Infinity);
      // what it meets is the route itself: not the valley drawn on past its finish, nor -- beside it -- its road down a
      // tunnel's ramp between walls, which a street beside keeps the ground over; on the route's road, under it
      const ramp = T.route.tunnels && n.d >= W / 2 + .3 && cutGround(T, n.s) != null && overTunnel(T, n.s) == null;
      if (n.d > W / 2 + 22 || n.s > T.L || ramp || (up && up[i] > -Infinity && toJoin(i) > 30)) return g;
      // over a tunnel the street keeps the ground line; under the route's own road a hand's breadth below it, so the
      // two never flicker; off its edge rising to it over 22 m, and never under the land beside it
      const top = overTunnel(T, n.s);
      if (top != null) return top + .05;
      if (n.d < W / 2 + .3) return n.y - .05;
      return Math.max(n.y + (g - n.y) * clamp((n.d - W / 2) / 22, 0, 1), n.d > W / 2 + ROAD_JOIN_M ? land : -Infinity);
    };
    // beside a tunnel's ramp a street runs up to its wall, never over its cutting: narrower where its edge would be
    // (Central loop's, by 0.6 m, hung 3 m over the road down the ramp)
    const half = p => {
      const n = routeNearest(T, p.x, p.z);
      if (!T.route.tunnels || cutGround(T, n.s) == null || overTunnel(T, n.s) != null) return r.w / 2;
      return clamp(n.d - W / 2 - RAMP_WALL_GAP_M, ROAD_NARROWEST_HALF_M, r.w / 2);
    };
    band(P, I, q, half, height);
    if (!up) return;
    // a ramp up to a bridge stands between retaining walls, from the ground to a parapet over the road
    for (const side of [-1, 1]) {
      let run = [];
      q.forEach((p, i) => {
        const a = q[Math.max(0, i - 1)], b = q[Math.min(q.length - 1, i + 1)], L = Math.hypot(b.x - a.x, b.z - a.z) || 1;
        const e = { x: p.x - (b.z - a.z) / L * (r.w / 2 + .15) * side, z: p.z + (b.x - a.x) / L * (r.w / 2 + .15) * side };
        const y = height(e, i), g = ground(e.x, e.z);
        if (y > g + .3) run.push({ x: e.x, z: e.z, y0: g - ROOT_M, y1: y + .9 });
        else { if (run.length > 1) wallOf(WP, WI, run, .3); run = []; }
      });
      if (run.length > 1) wallOf(WP, WI, run, .3);
    }
  });
  meshOf(G, WP, WI, new THREE.MeshLambertMaterial({ color: 0xb9b6ae, side: THREE.DoubleSide }), 'ramps');
  return meshOf(G, P, I, new THREE.MeshLambertMaterial({ color: 0x55575b, side: THREE.DoubleSide }), 'roads');
}
// The route's own road going on past where the route turns back on it -- a road marked "onward", on from where the turn
// begins: as wide as the route's road and marked as it is (the shoulders the route's road has where it is ridden one
// way only, it has none: ridden there and back, its road is all it takes); level with the route where it leaves it,
// then on the land as the route's road lies over it, the ground drawn ROAD_OVER_LAND_M under it (terrainH)
// it begins ONWARD_LEAD_M before the turn, a centimetre under the route's own road, which gives way to it from there
// (scripts/virtual_ride/turn_on_road.py): the route's road ends where its points do, up to 4 m apart, and left a gap
const ROAD_OVER_LAND_M = 1.2, ONWARD_BLEND_M = 60, ONWARD_LEAD_M = 6;
function addOnwardRoads(G, T, W, roads, ground, roadMat) {
  const P = [], U = [], I = [];
  roads.forEach(r => {
    const q = along(r.pts.map(p => xzOf(T, p)), 4), from = routeNearest(T, q[0].x, q[0].z).y, cum = [0];
    for (let i = 1; i < q.length; i++) cum.push(cum[i - 1] + Math.hypot(q[i].x - q[i - 1].x, q[i].z - q[i - 1].z));
    const ys = q.map((p, i) => { const k = clamp(cum[i] / ONWARD_BLEND_M, 0, 1); return from + (ground(p.x, p.z) + ROAD_OVER_LAND_M - from) * k * k * (3 - 2 * k); });
    const base = P.length / 3;
    q.forEach((p, i) => {
      const a = q[Math.max(0, i - 1)], b = q[Math.min(q.length - 1, i + 1)], L = Math.hypot(b.x - a.x, b.z - a.z) || 1, rx = -(b.z - a.z) / L, rz = (b.x - a.x) / L;
      P.push(p.x - rx * r.w / 2, ys[i] + .05, p.z - rz * r.w / 2, p.x + rx * r.w / 2, ys[i] + .05, p.z + rz * r.w / 2);
      U.push(0, cum[i] / 9, 1, cum[i] / 9); // the route's road's markings, 9 m a repeat (js/world.js ribbon)
      if (i) { const v = base + i * 2; I.push(v - 2, v - 1, v, v - 1, v + 1, v); }
    });
  });
  if (!I.length) return;
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(P, 3)); g.setAttribute('uv', new THREE.Float32BufferAttribute(U, 2));
  g.setIndex(I); g.computeVertexNormals();
  const m = new THREE.Mesh(g, roadMat); m.name = 'onward'; G.add(m);
}
// Which of the route's points lie on a road going on past its turn: where the route's own line leaves the road's middle
// for the rider's lane round the turn, the road is that one, not the route's (1 a point on it, else 0)
function onwardCover(T, roads, W) {
  const out = new Uint8Array(T.N);
  roads.forEach(r => {
    const q = r.pts.map(p => xzOf(T, p));
    for (let i = 0; i < T.N; i++) {
      for (let j = 0, cum = 0; j + 1 < q.length; j++) {
        const a = q[j], b = q[j + 1], dx = b.x - a.x, dz = b.z - a.z, L = Math.hypot(dx, dz) || 1, f = ((T.X[i] - a.x) * dx + (T.Z[i] - a.z) * dz) / (L * L);
        const on = f >= 0 && f <= 1 && cum + f * L >= ONWARD_LEAD_M; // short of that, the route's own road
        cum += L;
        if (on && Math.hypot(T.X[i] - a.x - dx * f, T.Z[i] - a.z - dz * f) < W / 2) { out[i] = 1; break; }
      }
    }
  });
  return out;
}
// The roads that climb onto a bridge over the route. OpenStreetMap draws a bridge apart from the roads that lead to
// it, so the road touching an end of a road bridge's deck goes down from the deck at RAMP_GRADE to the ground, and on
// into the next road where the ramp runs on past a junction. Per road, the ramp's height at each of its points (as
// `along` lays them, 5 m apart), or null for a road on the ground.
const RAMP_GRADE = .06, TOUCH_M = 2.5;
function rampsOf(T, roads, decks, ground) {
  const lines = roads.map(r => along(r.pts.map(p => xzOf(T, p)), 5)), out = roads.map(() => null);
  // the highest ramp yet that set off from each road's end: a lower one from the same end has nothing to add, and a
  // road between two bridges takes the ramp of each, from its own end
  const best = new Map(), queue = decks.filter(d => !d.b.foot).flatMap(d => [d.q[0], d.q[d.q.length - 1]].map(p => ({ x: p.x, z: p.z, y: d.deck })));
  while (queue.length) {
    const end = queue.shift();
    lines.forEach((q, k) => [0, q.length - 1].forEach(e => {
      const key = k + ':' + e;
      if (Math.hypot(q[e].x - end.x, q[e].z - end.z) > TOUCH_M || end.y <= (best.get(key) ?? -Infinity) + .01) return;
      best.set(key, end.y);
      const step = e ? -1 : 1, far = e ? 0 : q.length - 1;
      let s = 0, y = end.y;
      for (let i = e; ; i += step) {
        if (i !== e) s += Math.hypot(q[i].x - q[i - step].x, q[i].z - q[i - step].z);
        y = end.y - RAMP_GRADE * s;
        if (y <= ground(q[i].x, q[i].z)) return;
        const h = out[k] || (out[k] = new Float32Array(q.length).fill(-Infinity));
        h[i] = Math.max(h[i], y);
        if (i === far) break;
      }
      best.set(k + ':' + far, Math.max(best.get(k + ':' + far) ?? -Infinity, y)); // not back down the same road
      queue.push({ x: q[far].x, z: q[far].z, y }); // the ramp runs on past the junction
    }));
  }
  return out;
}

// --- what crosses over the route: a footbridge or a road's bridge, its deck clear of the route's road
// Each bridge's deck: its line, 2 m apart, and its height -- clear of the highest of the road under it, across its
// whole width (a wide one crossing a road that climbs spans a stretch of it); none for one not over the road
function overDecks(T, W, list) {
  return list.flatMap(b => {
    const q = along(b.pts.map(p => xzOf(T, p)), 2), h = b.w / 2;
    let top = -Infinity;
    q.forEach((p, i) => {
      const a = q[Math.max(0, i - 1)], c = q[Math.min(q.length - 1, i + 1)], L = Math.hypot(c.x - a.x, c.z - a.z) || 1;
      for (const k of [-1, 0, 1]) { const n = routeNearest(T, p.x - (c.z - a.z) / L * h * k, p.z + (c.x - a.x) / L * h * k); if (n.d < W / 2 + 1.5) top = Math.max(top, n.y); }
    });
    return Number.isFinite(top) ? [{ b, q, deck: top + (b.foot ? 5.4 : 6) }] : [];
  });
}
function addOverpasses(G, T, W, decks, ground) {
  const P = [], I = [], RP = [], RI = [], piers = [], conc = new THREE.MeshLambertMaterial({ color: 0xb9b6ae, side: THREE.DoubleSide });
  decks.forEach(({ b, q, deck }) => {
    const h = b.w / 2, th = b.foot ? .6 : 1.2;
    // the deck -- a road's in the asphalt of the roads that climb onto it -- its underside and its two parapets
    if (b.foot) band(P, I, q, h, () => deck); else band(RP, RI, q, h, () => deck);
    band(P, I, q, h, () => deck - th);
    for (const k of [-1, 1]) {
      const rail = q.map((p, i) => {
        const a = q[Math.max(0, i - 1)], c = q[Math.min(q.length - 1, i + 1)], L = Math.hypot(c.x - a.x, c.z - a.z) || 1;
        return { x: p.x - (c.z - a.z) / L * h * k, z: p.z + (c.x - a.x) / L * h * k, y0: deck - th, y1: deck + 1.1 };
      });
      wallOf(P, I, rail, .2);
    }
    // piers beside the road and at the ends, where a bridge stands on the ground
    q.forEach((p, i) => {
      const n = routeNearest(T, p.x, p.z), end = i === 0 || i === q.length - 1;
      if (end || (n.d > W / 2 + 1.2 && n.d < W / 2 + 3.2 && i % 2 === 0)) piers.push({ x: p.x, z: p.z, y: ground(p.x, p.z) - ROOT_M, h: deck - th - ground(p.x, p.z) + ROOT_M, w: end && b.foot ? 3 : 1 });
    });
  });
  meshOf(G, P, I, conc, 'overpasses');
  meshOf(G, RP, RI, new THREE.MeshLambertMaterial({ color: 0x55575b, side: THREE.DoubleSide }), 'overpass-roads');
  if (!piers.length) return;
  const bg = new THREE.BoxGeometry(1, 1, 1); bg.translate(0, .5, 0);
  const im = new THREE.InstancedMesh(bg, conc, piers.length), M = new THREE.Matrix4();
  piers.forEach((p, i) => im.setMatrixAt(i, M.makeScale(p.w, p.h, p.w).setPosition(p.x, p.y, p.z)));
  im.name = 'piers'; G.add(im);
}

// --- the route's own bridges and tunnels: parapets along a bridge's edges; a tunnel's walls up its ramps to the
// ground line and its roof, the crossing street's deck
function addRouteStructures(G, T, W, ground) {
  const P = [], I = [], o = {};
  const edge = (s0, s1, off, y0, y1) => {
    const pts = [];
    for (let s = s0; s <= s1 + 1e-6; s += 2) { sampleAt(T, s, o); pts.push({ x: o.x + o.rx * off, z: o.z + o.rz * off, y0: y0(s, o), y1: y1(s, o) }); }
    wallOf(P, I, pts, .35);
  };
  (T.route.bridges || []).forEach(([i0, i1]) => {
    const s0 = T.ptS[i0] - 6, s1 = T.ptS[i1] + 6;
    for (const k of [-1, 1]) edge(s0, s1, k * (W / 2 + .3), (s, p) => p.y - .6, (s, p) => p.y + 1.05);
  });
  tunnelZones(T).forEach(z => {
    for (const k of [-1, 1]) edge(z.s0, z.s1, k * (W / 2 + .35), (s, p) => p.y - .3, s => cutGround(T, s) + 1);
    // the roof over the tunnel, a metre thick, its face to the road under it
    const roof = [];
    for (let s = z.p0; s <= z.p1 + 1e-6; s += 2) { sampleAt(T, s, o); roof.push({ x: o.x, z: o.z }); }
    band(P, I, roof, W / 2 + .7, p => cutGround(T, routeNearest(T, p.x, p.z).s) - 1);
    band(P, I, roof, W / 2 + .7, p => cutGround(T, routeNearest(T, p.x, p.z).s) - .05);
    // at each portal the roof's face over the road and the crossing street's parapet on it: a rider riding under it
    // sees a bridge, not two sheets with the street beyond showing between them
    for (const s of [z.p0, z.p1]) {
      sampleAt(T, s, o);
      const c = cutGround(T, s), h = W / 2 + .7;
      wallOf(P, I, [-1, 1].map(k => ({ x: o.x + o.rx * h * k, z: o.z + o.rz * h * k, y0: c - 1, y1: c + 1.05 })), .35);
    }
  });
  meshOf(G, P, I, new THREE.MeshLambertMaterial({ color: 0xc2beb4, side: THREE.DoubleSide }), 'structures');
}

// --- roads that go under the route: down a cutting between retaining walls to clear its road
function addUnderpasses(G, T, W, list, ground) {
  const P = [], I = [], W2 = [], WI = [];
  list.forEach(u => {
    const q0 = u.pts.map(p => xzOf(T, p)), a = q0[0], b = q0[q0.length - 1], L = Math.hypot(b.x - a.x, b.z - a.z) || 1, ux = (b.x - a.x) / L, uz = (b.z - a.z) / L;
    // the cutting runs on 110 m past either end, where a 6% ramp comes up from under the road
    const q = along([{ x: a.x - ux * 110, z: a.z - uz * 110 }, ...q0, { x: b.x + ux * 110, z: b.z + uz * 110 }], 3);
    let cross = null;
    q.forEach(p => { const n = routeNearest(T, p.x, p.z); if (!cross || n.d < cross.d) cross = { d: n.d, y: n.y, x: p.x, z: p.z }; });
    if (!cross || cross.d > W) return;
    const floor = p => Math.min(ground(p.x, p.z) + .02, cross.y - 6.5 + Math.max(0, Math.hypot(p.x - cross.x, p.z - cross.z) - u.w / 2 - W / 2 - 4) * .06);
    const deep = q.filter(p => floor(p) < ground(p.x, p.z) - .3);
    if (deep.length < 2) return;
    band(P, I, deep, u.w / 2, floor);
    for (const k of [-1, 1]) {
      const pts = deep.map((p, i) => {
        const c0 = deep[Math.max(0, i - 1)], c1 = deep[Math.min(deep.length - 1, i + 1)], LL = Math.hypot(c1.x - c0.x, c1.z - c0.z) || 1;
        const x = p.x - (c1.z - c0.z) / LL * (u.w / 2 + .3) * k, z = p.z + (c1.x - c0.x) / LL * (u.w / 2 + .3) * k;
        return { x, z, y0: floor(p) - .2, y1: ground(x, z) + .9 };
      });
      wallOf(W2, WI, pts, .35);
    }
  });
  meshOf(G, P, I, new THREE.MeshLambertMaterial({ color: 0x55575b, side: THREE.DoubleSide }), 'underpasses');
  meshOf(G, W2, WI, new THREE.MeshLambertMaterial({ color: 0xc2beb4, side: THREE.DoubleSide }), 'cuttings');
}

// --- lines seen from the road: power lines on towers or poles, their wires sagging; railways on their ballast
const LINE_REACH = 1500; // as far as the scenery's ground: further out they would hang over the plain
const LINE_CLEAR_M = 6;
function addLines(G, T, lines, ground) {
  const towers = [], poles = [], wires = [], P = [], I = [], rails = [];
  lines.forEach(l => {
    const q = l.pts.map(p => xzOf(T, p));
    if (!q.some(p => routeGap(T, p.x, p.z) < LINE_REACH)) return;
    if (l.k === 'rail') {
      const pts = along(q, 6).filter(p => routeGap(T, p.x, p.z) < LINE_REACH);
      band(P, I, pts, 1.8, p => ground(p.x, p.z) + .12);
      for (const k of [-.75, .75]) for (let i = 0; i + 1 < pts.length; i++) {
        const a = pts[i], b = pts[i + 1], L = Math.hypot(b.x - a.x, b.z - a.z) || 1, nx = -(b.z - a.z) / L * k, nz = (b.x - a.x) / L * k;
        rails.push(a.x + nx, ground(a.x, a.z) + .3, a.z + nz, b.x + nx, ground(b.x, b.z) + .3, b.z + nz);
      }
      return;
    }
    const power = l.k === 'power', h = power ? 26 : 9, arm = power ? [-4.2, 0, 4.2] : [-.6, .6];
    const stands = q.filter(p => routeGap(T, p.x, p.z) < LINE_REACH && routeGap(T, p.x, p.z) > T.route.width / 2 + 3).map(p => ({ x: p.x, z: p.z, y: ground(p.x, p.z) }));
    stands.forEach((p, i) => {
      const nb = stands[Math.min(stands.length - 1, i + 1)], pb = stands[Math.max(0, i - 1)];
      p.rot = Math.atan2(nb.x - pb.x, nb.z - pb.z);
      (power ? towers : poles).push(p);
    });
    // a span over the route's road keeps its wires LINE_CLEAR_M over it: the stands either side rise as it asks --
    // a gorge's line from the valley's floor up across a road on its side hung 4.7 m over it
    const sagOf = span => Math.min(power ? 6 : 1.5, span * span / 30000);
    const wireY = (a, b, f, sag) => a.y + (a.lift || 0) + h - 1 + (b.y + (b.lift || 0) - a.y - (a.lift || 0)) * f - sag * 4 * f * (1 - f);
    for (let i = 0; i + 1 < stands.length; i++) {
      const a = stands[i], b = stands[i + 1], span = Math.hypot(b.x - a.x, b.z - a.z);
      if (span > 600) continue;
      let need = 0;
      for (let k = 0; k <= 32; k++) {
        const f = k / 32, x = a.x + (b.x - a.x) * f, z = a.z + (b.z - a.z) * f, n = routeNearest(T, x, z);
        if (n.d < T.route.width / 2 + 1) need = Math.max(need, LINE_CLEAR_M - (wireY(a, b, f, sagOf(span)) - n.y));
      }
      if (need > 0) { a.lift = Math.max(a.lift || 0, need); b.lift = Math.max(b.lift || 0, need); }
    }
    for (let i = 0; i + 1 < stands.length; i++) {
      const a = stands[i], b = stands[i + 1], span = Math.hypot(b.x - a.x, b.z - a.z);
      if (span > 600) continue; // a line that leaves the scenery and comes back is not one wire
      const sag = sagOf(span);
      for (const off of arm) {
        const ax = a.x + Math.cos(a.rot) * off, az = a.z - Math.sin(a.rot) * off, bx = b.x + Math.cos(b.rot) * off, bz = b.z - Math.sin(b.rot) * off;
        for (let k = 0; k < 8; k++) {
          const f0 = k / 8, f1 = (k + 1) / 8, y = f => wireY(a, b, f, sag);
          wires.push(ax + (bx - ax) * f0, y(f0), az + (bz - az) * f0, ax + (bx - ax) * f1, y(f1), az + (bz - az) * f1);
        }
      }
    }
  });
  meshOf(G, P, I, new THREE.MeshLambertMaterial({ color: 0x7d746a }), 'ballast');
  const seg = (arr, colour, name) => {
    if (!arr.length) return;
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(arr, 3));
    const m = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: colour })); m.name = name; G.add(m);
  };
  seg(wires, 0x3d4045, 'wires'); seg(rails, 0x5a5550, 'rails');
  const stand = (list, geo, sx, sy, colour, name, lattice) => {
    if (!list.length) return;
    const im = new THREE.InstancedMesh(geo, new THREE.MeshLambertMaterial({ color: colour, wireframe: !!lattice }), list.length), M = new THREE.Matrix4(), Q = new THREE.Quaternion(), S = new THREE.Vector3(sx, sy, sx), V = new THREE.Vector3(), up = new THREE.Vector3(0, 1, 0);
    // a stand risen for a span over the road: a tower or a pole taller, an arm higher
    list.forEach((p, i) => { Q.setFromAxisAngle(up, p.rot); V.set(p.x, p.y - ROOT_M + (sy === 1 ? p.lift || 0 : 0), p.z); S.set(sx, sy === 1 ? 1 : sy + (p.lift || 0), sx); M.compose(V, Q, S); im.setMatrixAt(i, M); });
    im.name = name; G.add(im);
  };
  // a lattice tower as a slim four-sided spire with its cross-arm; a pole as a post with its own
  const tower = new THREE.CylinderGeometry(.25, 2, 1, 4, 7, true); tower.translate(0, .5, 0);
  const armG = new THREE.BoxGeometry(9.4, .5, .5); armG.translate(0, 25, 0);
  const pole = new THREE.CylinderGeometry(.12, .18, 1, 6); pole.translate(0, .5, 0);
  stand(towers, tower, 1, 27, 0x8a8f94, 'towers', true); stand(towers, armG, 1, 1, 0x8a8f94, 'arms'); stand(poles, pole, 1, 9.3, 0x9a948a, 'poles');
}

// --- water: rivers and canals as bands at the ground, lakes and ponds flat at the lowest ground round them
function addWater(G, T, water, ground) {
  const P = [], I = [], mat = new THREE.MeshLambertMaterial({ color: 0x5d7c8c, side: THREE.DoubleSide });
  water.forEach(w => {
    if (w.area) {
      const ring = w.area.map(p => xzOf(T, p));
      if (!ring.some(p => routeGap(T, p.x, p.z) < LINE_REACH) || ring.length < 3) return;
      const y = Math.min(...ring.map(p => ground(p.x, p.z))) + .05;
      let tris = []; try { tris = THREE.ShapeUtils.triangulateShape(ring.map(p => new THREE.Vector2(p.x, p.z)), []); } catch (e) { return; }
      const base = P.length / 3; ring.forEach(p => P.push(p.x, y, p.z)); tris.forEach(t => I.push(base + t[0], base + t[1], base + t[2]));
      return;
    }
    const pts = along(w.pts.map(p => xzOf(T, p)), 6).filter(p => routeGap(T, p.x, p.z) < LINE_REACH && routeGap(T, p.x, p.z) > T.route.width / 2 + 1);
    // a river under the route's road is cut where it passes under it: each run of points on its own
    let run = [];
    const flush = () => { if (run.length > 1) band(P, I, run, w.w / 2, p => ground(p.x, p.z) + .04); run = []; };
    pts.forEach((p, i) => { if (i && Math.hypot(p.x - pts[i - 1].x, p.z - pts[i - 1].z) > 12) flush(); run.push(p); });
    flush();
  });
  meshOf(G, P, I, mat, 'water');
}

// whether (x, z) lies on one of the roads round the route, m metres to spare: no tree or house stands there
function roadsNear(T, roads) {
  const cell = 30, g = new Map(), segs = [];
  (roads || []).forEach(r => {
    const q = r.pts.map(p => xzOf(T, p));
    for (let i = 0; i + 1 < q.length; i++) {
      const a = q[i], b = q[i + 1], k = segs.push({ a, b, h: r.w / 2 }) - 1;
      for (let x = Math.floor(Math.min(a.x, b.x) / cell) - 1; x <= Math.floor(Math.max(a.x, b.x) / cell) + 1; x++)
        for (let z = Math.floor(Math.min(a.z, b.z) / cell) - 1; z <= Math.floor(Math.max(a.z, b.z) / cell) + 1; z++) { const key = x + ',' + z; (g.get(key) || g.set(key, []).get(key)).push(k); }
    }
  });
  return (x, z, m) => (g.get(Math.floor(x / cell) + ',' + Math.floor(z / cell)) || []).some(k => { const { a, b, h } = segs[k]; return segDist(x, z, a.x, a.z, b.x, b.z) < h + m; });
}

// How much land lies beside the road at each of its points before another stretch of the same route running
// alongside it -- a dual carriageway's other half, a road ridden back: [left, right], Infinity where none comes near,
// below 0 where the two are one road. A stretch that crosses it is no neighbour. A strip between two stretches
// belongs to the earlier one (room.first), so it is drawn once.
function roomBeside(T, W) {
  routeGap(T, 0, 0); // lays the route's grid
  const room = [new Float32Array(T.N).fill(Infinity), new Float32Array(T.N).fill(Infinity)];
  const first = [new Uint8Array(T.N), new Uint8Array(T.N)], gap = 2 * W + 20, k = Math.ceil((W + 16) / ROUTE_CELL), o = {};
  for (let i = 0; i < T.N; i++) {
    sampleAt(T, T.D[i], o);
    const cx = Math.floor(T.X[i] / ROUTE_CELL), cz = Math.floor(T.Z[i] / ROUTE_CELL);
    for (let a = -k; a <= k; a++) for (let b = -k; b <= k; b++) for (const j of T.grid.get((cx + a) + ',' + (cz + b)) || []) {
      let back = Math.abs(T.D[i] - T.D[j]); if (T.loop) back = Math.min(back, T.L - back);
      const dx = T.X[j] - T.X[i], dz = T.Z[j] - T.Z[i], k2 = Math.min(T.N - 1, j + 1), k1 = k2 - 1;
      const tl = Math.hypot(T.X[k2] - T.X[k1], T.Z[k2] - T.Z[k1]) || 1;
      if (back <= gap || Math.abs(dx * o.tx + dz * o.tz) > 3) continue;
      if (Math.abs(((T.X[k2] - T.X[k1]) * o.tx + (T.Z[k2] - T.Z[k1]) * o.tz) / tl) < .9) continue; // crossing, not alongside
      const lat = dx * o.rx + dz * o.rz, side = lat > 0 ? 1 : 0, free = Math.abs(lat) - W;
      if (free < room[side][i]) { room[side][i] = free; first[side][i] = T.D[i] < T.D[j] ? 1 : 0; }
    }
  }
  // the narrowest within 8 m either way, then eased over 24 m: a strip's edge runs smooth, and never wider than it is
  const ease = a => {
    const n = a.length, at = i => a[T.loop ? ((i % n) + n) % n : clamp(i, 0, n - 1)], low = new Float32Array(n), out = new Float32Array(n);
    for (let i = 0; i < n; i++) { let m = Infinity; for (let k = -2; k <= 2; k++) m = Math.min(m, at(i + k)); low[i] = m; }
    const lo = i => low[T.loop ? ((i % n) + n) % n : clamp(i, 0, n - 1)];
    for (let i = 0; i < n; i++) { let sum = 0, c = 0, m = lo(i); for (let k = -3; k <= 3; k++) { const v = lo(i + k); if (Number.isFinite(v)) { sum += v; c++; } } out[i] = Number.isFinite(m) && c ? Math.min(m + 1, sum / c) : m; }
    return out;
  };
  const eased = [ease(room[0]), ease(room[1])];
  eased.first = first;
  return eased;
}
// a dual carriageway's narrow median, from half a metre to 4 m: a concrete barrier down its middle, broken where the
// route turns across it
function addMedianBarriers(G, T, W, room) {
  const P = [], I = [], o = {}, turning = i => {
    const a = Math.max(0, i - 4), b = Math.min(T.N - 1, i + 4);
    const h0 = Math.atan2(T.Z[a + 1] - T.Z[a], T.X[a + 1] - T.X[a]), h1 = Math.atan2(T.Z[b] - T.Z[b - 1], T.X[b] - T.X[b - 1]);
    return Math.abs(((h1 - h0 + 3 * Math.PI) % (2 * Math.PI)) - Math.PI) > Math.PI / 4;
  };
  for (const k of [0, 1]) {
    let run = [];
    const flush = () => { if (run.length > 1) wallOf(P, I, run, .4); run = []; };
    for (let i = 0; i < T.N; i += 2) {
      const free = room[k][i];
      if (!(free >= .5 && free < 4) || !room.first[k][i] || T.again[i] || turning(i)) { flush(); continue; }
      sampleAt(T, T.D[i], o);
      const off = (k ? 1 : -1) * (W / 2 + free / 2);
      run.push({ x: o.x + o.rx * off, z: o.z + o.rz * off, y0: o.y - .2, y1: o.y + .85 });
    }
    flush();
  }
  meshOf(G, P, I, new THREE.MeshLambertMaterial({ color: 0xbdb9b0, side: THREE.DoubleSide }), 'median');
}
