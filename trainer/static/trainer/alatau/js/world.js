'use strict';
/* ---------------- Мир: рельеф, дорога, здания, деревья, горы, старт и финиш ---------------- */
let scenery = null; // the 3D world drawn along the course being ridden
function disposeWorld() {
  if (!scenery) return;
  scene.remove(scenery);
  scenery.traverse(o => { if (o.geometry) o.geometry.dispose(); [].concat(o.material || []).forEach(m => { if (m === buildingMat || m === treeMat || m === osmMat) return; if (m.map) m.map.dispose(); m.dispose(); }); });
  scenery = null; world = null;
}
// A grid of heights (js/maps.js) at a latitude and longitude, or null outside it
function gridAt(g, lat, lon) {
  const [la0, dla, nr] = g.lat, [lo0, dlo, nc] = g.lon, fi = (lat - la0) / dla, fj = (lon - lo0) / dlo;
  if (fi < 0 || fj < 0 || fi > nr - 1 || fj > nc - 1) return null;
  const i = Math.min(nr - 2, Math.floor(fi)), j = Math.min(nc - 2, Math.floor(fj)), u = fi - i, v = fj - j, H = g.h;
  return H[i * nc + j] * (1 - u) * (1 - v) + H[(i + 1) * nc + j] * u * (1 - v) + H[i * nc + j + 1] * (1 - u) * v + H[(i + 1) * nc + j + 1] * u * v;
}
// The map's SRTM ground at (x, z) on the route's metres, or null outside its grid: a detail grid where one covers
// the place, else the map's own (js/maps.js); over a detail grid's outer DETAIL_FADE cells it gives way to the grid
// under it, where it ended in a step (Medeu's in four city sceneries, up to 34 m)
const DETAIL_FADE = 3;
function reliefAt(T, x, z) {
  const rel = mapOf(T.route).relief;
  if (!rel) return null;
  const { lat, lon } = unproj(x, z, T.origin), grids = (rel.detail || []).concat([rel]);
  const at = k => {
    if (k >= grids.length) return null;
    const g = grids[k], h = gridAt(g, lat, lon);
    if (h == null) return at(k + 1);
    if (k === grids.length - 1) return h;
    const fi = (lat - g.lat[0]) / g.lat[1], fj = (lon - g.lon[0]) / g.lon[1];
    const inside = Math.min(fi, fj, g.lat[2] - 1 - fi, g.lon[2] - 1 - fj) / DETAIL_FADE;
    if (inside >= 1) return h;
    const under = at(k + 1);
    return under == null ? h : under + (h - under) * inside;
  };
  return at(0);
}
// The far relief's own surface at (x, z): the map's grid alone, on the two triangles a cell is drawn as -- split from
// its next column's corner to its next row's, as addRelief lays them -- lowered by the Earth's curve
function farReliefAt(T, x, z) {
  const rel = mapOf(T.route).relief;
  if (!rel) return null;
  const { lat, lon } = unproj(x, z, T.origin), [la0, dla, nr] = rel.lat, [lo0, dlo, nc] = rel.lon, fi = (lat - la0) / dla, fj = (lon - lo0) / dlo;
  if (fi < 0 || fj < 0 || fi > nr - 1 || fj > nc - 1) return null;
  const i = Math.min(nr - 2, Math.floor(fi)), j = Math.min(nc - 2, Math.floor(fj)), u = fi - i, v = fj - j, H = rel.h, at = (a, b) => H[(i + a) * nc + j + b];
  const h = u + v <= 1 ? at(0, 0) + (at(1, 0) - at(0, 0)) * u + (at(0, 1) - at(0, 0)) * v : at(1, 1) + (at(0, 1) - at(1, 1)) * (1 - u) + (at(1, 0) - at(1, 1)) * (1 - v);
  return h - (x * x + z * z) / (2 * EARTH_R) * REFRACTION;
}
// A route's land: under the road a little below it, and away from it, over 80 to 580 m, the ground SRTM has there --
// the hills and slopes round a city's or the steppe's roads; a gorge's walls rise from 6 to 66 m off its road, its
// road in SRTM's valley (Medeu's within metres of it); a gorge on a map without a relief has walls drawn for it
const RELIEF_FROM = 80, RELIEF_OVER = 500, GORGE_FROM = 6, GORGE_OVER = 60;
// a gorge's land snowy from SNOW_FROM_M, white from SNOW_WHOLE_M: the Cosmostation's top white, as the maintainer likes it
const SNOW_FROM_M = 3000, SNOW_WHOLE_M = 3200;
// and stone with no grass from ROCK_WHOLE_M, the grass thinning out from ROCK_FROM_M: past the border guards' post on
// the way to the Cosmostation, as the maintainer remembers it
const ROCK_FROM_M = 2600, ROCK_WHOLE_M = 2800;
function terrainH(T, x, z, near) {
  const n = near || nearest(T, x, z); let h = n.y - 1.2; // near: the route's nearest point, when the caller has it
  // round a tunnel and its ramps the land keeps the ground line up to their walls: the road goes down into a cutting,
  // the ground does not; inside the walls the land is left out (landMaterial)
  const cut = T.route.tunnels ? cutGround(T, n.s) : null;
  if (cut != null) h = cut - 1.2;
  if (T.route.scenery !== 'gorge') {
    const far = n.d > T.route.width / 2 + RELIEF_FROM ? reliefAt(T, x, z) : null;
    if (far != null) { const k = clamp((n.d - T.route.width / 2 - RELIEF_FROM) / RELIEF_OVER, 0, 1); h += (far - 1.2 - h) * k * k * (3 - 2 * k); }
  }
  if (T.route.scenery === 'gorge') {
    const real = reliefAt(T, x, z);
    if (real != null) { const k = clamp((n.d - T.route.width / 2 - GORGE_FROM) / GORGE_OVER, 0, 1); h += (real - 1.2 - h) * k * k * (3 - 2 * k); }
    else if (n.d > 45) { const k = n.d - 45, f = clamp((n.s - 1200) / 3000, .12, 1); h += f * (k * .46 + fbm(x * .004, z * .004) * Math.min(1, k / 120) * 70); }
  } else if (n.d > 70) { h += (fbm(x * .003, z * .003) - .5) * 5 * Math.min(1, (n.d - 70) / 250); }
  return h;
}
// The ground as drawn: the height of the terrain's grid at a point, each cell split along the diagonal three.js's
// PlaneGeometry splits it on, (ix, iz+1)-(ix+1, iz). terrainH is the shape the grid samples; between its vertices,
// tens of metres apart, the drawn ground is a plane and can sit metres above or below it.
function groundOf(pos, x0, z0, x1, z1, nx, nz) {
  const w = nx + 1, y = (ix, iz) => pos.getY(ix + w * iz);
  return (x, z) => {
    const fx = clamp((x - x0) / (x1 - x0) * nx, 0, nx - 1e-6), fz = clamp((z - z0) / (z1 - z0) * nz, 0, nz - 1e-6);
    const ix = Math.floor(fx), iz = Math.floor(fz), u = fx - ix, v = fz - iz;
    const a = y(ix, iz), b = y(ix, iz + 1), c = y(ix + 1, iz + 1), d = y(ix + 1, iz);
    return u + v <= 1 ? a + (d - a) * u + (b - a) * v : c + (b - c) * (1 - u) + (d - c) * (1 - v);
  };
}
// The ground under the road and beside it, wide metres across, kept 10 cm below them: between the grid's vertices,
// tens of metres apart, the ground is a plane, and one leaning on a gorge's wall rose over the road (Medeu's, by up to
// 4 m). Where it does, its three vertices go down together as far as it rose; a tunnel's cutting is left as it is.
function sinkUnderRoad(T, pos, x0, z0, x1, z1, nx, nz, wide) {
  const w = nx + 1, o = {}, drawn = groundOf(pos, x0, z0, x1, z1, nx, nz);
  for (let s = 0; s <= T.L; s += 2) {
    if (T.route.tunnels && cutGround(T, s) != null) continue;
    sampleAt(T, s, o);
    for (let off = -wide / 2; off <= wide / 2 + 1e-6; off += 1) {
      const x = o.x + o.rx * off, z = o.z + o.rz * off, over = drawn(x, z) - (o.y - .1);
      if (over <= 0) continue;
      const fx = clamp((x - x0) / (x1 - x0) * nx, 0, nx - 1e-6), fz = clamp((z - z0) / (z1 - z0) * nz, 0, nz - 1e-6);
      const ix = Math.floor(fx), iz = Math.floor(fz), first = fx - ix + fz - iz <= 1;
      for (const [a, b] of first ? [[ix, iz], [ix, iz + 1], [ix + 1, iz]] : [[ix + 1, iz + 1], [ix, iz + 1], [ix + 1, iz]]) pos.setY(a + w * b, pos.getY(a + w * b) - over);
    }
  }
}
// The ground under a sight that lies flat on it (PADS, js/landmarks.js): inside its ring and within its margin, no
// higher than its level -- a rink in a valley's bowl, where the land had covered its ice by up to 22 m.
function sinkUnderPad(pos, x0, z0, x1, z1, nx, nz, pad) {
  const xs = pad.ring.map(p => p[0]), zs = pad.ring.map(p => p[1]), m = pad.margin, n = pad.ring.length;
  const inside = (x, z) => { let c = false; for (let i = 0, j = n - 1; i < n; j = i++) { const [xi, zi] = pad.ring[i], [xj, zj] = pad.ring[j]; if ((zi > z) !== (zj > z) && x < (xj - xi) * (z - zi) / (zj - zi) + xi) c = !c; } return c; };
  const edge = (x, z) => { let d = Infinity; for (let i = 0, j = n - 1; i < n; j = i++) d = Math.min(d, segDist(x, z, pad.ring[j][0], pad.ring[j][1], pad.ring[i][0], pad.ring[i][1])); return d; };
  const lx = Math.min(...xs) - m, hx = Math.max(...xs) + m, lz = Math.min(...zs) - m, hz = Math.max(...zs) + m;
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i), z = pos.getZ(i);
    if (x < lx || x > hx || z < lz || z > hz) continue;
    if (pos.getY(i) > pad.y && (inside(x, z) || edge(x, z) <= m)) pos.setY(i, pad.y);
  }
}
// A gorge's rivers run down: each along its OpenStreetMap way, which runs with the stream (turned round where it starts
// lower than it ends), never rising -- on the land it climbed onto the road's shelf and down again --, and the land
// under it and RIVER_BANK_M beside it cut down to RIVER_BED_M under it. The road's own triangles keep their land: cut,
// they left the road over a hollow its fills then filled. Its profile goes to addWater (T.rivers).
const RIVER_BED_M = .3, RIVER_BANK_M = 1;
function carveRivers(T, water, pos, x0, z0, x1, z1, nx, nz, wide) {
  const w1 = nx + 1, drawn = groundOf(pos, x0, z0, x1, z1, nx, nz), o = {}, keep = new Set();
  const corners = (x, z) => {
    const fx = clamp((x - x0) / (x1 - x0) * nx, 0, nx - 1e-6), fz = clamp((z - z0) / (z1 - z0) * nz, 0, nz - 1e-6);
    const ix = Math.floor(fx), iz = Math.floor(fz), first = fx - ix + fz - iz <= 1;
    return (first ? [[ix, iz], [ix, iz + 1], [ix + 1, iz]] : [[ix + 1, iz + 1], [ix, iz + 1], [ix + 1, iz]]).map(([a, b]) => a + w1 * b);
  };
  for (let s = 0; s <= T.L; s += 2) {
    sampleAt(T, s, o);
    for (let off = -wide / 2; off <= wide / 2 + 1e-6; off += 1) corners(o.x + o.rx * off, o.z + o.rz * off).forEach(i => keep.add(i));
  }
  T.rivers = new Map();
  water.forEach(w => {
    if (w.area || !w.pts) return;
    let pts = along(w.pts.map(p => xzOf(T, p)), 6).filter(p => routeGap(T, p.x, p.z) < LINE_REACH);
    if (pts.length < 2) return;
    if (drawn(pts[0].x, pts[0].z) < drawn(pts[pts.length - 1].x, pts[pts.length - 1].z)) pts = pts.reverse();
    let y = Infinity;
    const profile = pts.map(p => { y = Math.min(y, drawn(p.x, p.z)); return { x: p.x, z: p.z, y }; });
    profile.forEach((p, i) => {
      const q = profile[Math.min(i + 1, profile.length - 1)], r = profile[Math.max(i - 1, 0)], dx = q.x - r.x, dz = q.z - r.z, l = Math.hypot(dx, dz) || 1;
      for (let off = -w.w / 2 - RIVER_BANK_M; off <= w.w / 2 + RIVER_BANK_M + 1e-6; off += 1) {
        corners(p.x - dz / l * off, p.z + dx / l * off).forEach(k => { if (!keep.has(k) && pos.getY(k) > p.y - RIVER_BED_M) pos.setY(k, p.y - RIVER_BED_M); });
      }
    });
    T.rivers.set(w, profile);
  });
  // a vertex cut for a stretch further down lies lower than this one's bed: the river follows the cut land down
  T.rivers.forEach(profile => { let y = Infinity; profile.forEach(p => { y = Math.min(y, p.y, drawn(p.x, p.z) + RIVER_BED_M); p.y = y; }); });
}
// how deep a trunk goes into the ground: a slope under it leaves no gap at its foot
const ROOT_M = .3, LAND_POINTS = 200000;
let world_osmKept = 0;
// the course to ride, and the scenery along it
function buildWorld(route) {
  disposeWorld();
  const course = buildCourse(route), { T, S0, FIN, lms } = course, grp = new THREE.Group(), r = rng(route.id.length * 977 + 13);
  // a racetrack lies in the steppe, its edges run-off and barriers: no tree stands along it
  const W = route.width, gorge = route.scenery === 'gorge', track = route.scenery === 'racetrack', steppe = track || route.scenery === 'steppe';
  // road ridden earlier, at a distance along the route: drawn once, and passed by the trees already planted on it
  const againAt = s => T.again[clamp(Math.round(s / T.L * (T.N - 1)), 0, T.N - 1)];
  // --- рельеф ---
  const margin = gorge ? 2400 : 1600;
  const x0 = T.minX - margin, x1 = T.maxX + margin, z0 = T.minZ - margin, z1 = T.maxZ + margin;
  // cells 40 m across, LAND_POINTS at most: a long route's land had cells 50 by 85 m, too coarse for a road cut into a
  // gorge's side (the Cosmostation's)
  const cell = Math.max(40, Math.sqrt((x1 - x0) * (z1 - z0) / LAND_POINTS));
  const nx = Math.ceil((x1 - x0) / cell), nz = Math.ceil((z1 - z0) / cell);
  const tg = new THREE.PlaneGeometry(x1 - x0, z1 - z0, nx, nz); tg.rotateX(-Math.PI / 2); tg.translate((x0 + x1) / 2, 0, (z0 + z1) / 2);
  const pos = tg.attributes.position, cols = new Float32Array(pos.count * 3);
  const shapes = lms.map(lm => SHAPES[lm.type] && SHAPES[lm.type](lm, T)).filter(Boolean); // sights the land takes the shape of
  const cGrass = new THREE.Color(0x7c8a58), cDust = new THREE.Color(0x9a9684), cForest = new THREE.Color(0x3c5536), cRock = new THREE.Color(0x837a6c), cSnow = new THREE.Color(0xeef2f5), tmp = new THREE.Color();
  const cDry = new THREE.Color(0xa49b67), cMeadow = new THREE.Color(0x8b8e58); // the steppe: dry grass, and greener hollows
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i), z = pos.getZ(i), n = nearest(T, x, z);
    let h = edgeLand(T, x, z, terrainH(T, x, z, n), x0, x1, z0, z1);
    for (const f of shapes) { const v = f(x, z); if (v != null && v > h) h = v; }
    pos.setY(i, h);
    const nz2 = fbm(x * .01, z * .01, 3);
    if (gorge) { const rise = h - n.y; tmp.copy(cForest).lerp(cGrass, clamp(1 - n.d / 120, 0, 1) * .6).lerp(cRock, clamp((rise - 250) / 350, 0, 1) * .8 + nz2 * .15); if (h > ROCK_FROM_M) tmp.lerp(cRock, clamp((h - ROCK_FROM_M) / (ROCK_WHOLE_M - ROCK_FROM_M), 0, 1)); if (h > SNOW_FROM_M) tmp.lerp(cSnow, clamp((h - SNOW_FROM_M) / (SNOW_WHOLE_M - SNOW_FROM_M), 0, 1)); }
    else if (steppe) tmp.copy(cDry).lerp(cMeadow, clamp(fbm(x * .0012, z * .0012, 3) * 1.6 - .45, 0, 1) * .85).lerp(cDust, clamp(1 - (n.d - W) / 30, 0, 1) * .5 + nz2 * .12);
    else tmp.copy(cGrass).lerp(cDust, clamp(1 - (n.d - W) / 60, 0, 1) * .7 + nz2 * .3);
    cols[i * 3] = tmp.r; cols[i * 3 + 1] = tmp.g; cols[i * 3 + 2] = tmp.b;
  }
  sinkUnderRoad(T, pos, x0, z0, x1, z1, nx, nz, W + 2 * (gorge || steppe ? 2.5 : 5));
  lms.forEach(lm => { const pad = PADS[lm.type] && PADS[lm.type](lm, T); if (pad) sinkUnderPad(pos, x0, z0, x1, z1, nx, nz, pad); });
  turningCircles(T, route).forEach(c => sinkUnderPad(pos, x0, z0, x1, z1, nx, nz, { ring: c.ring, margin: 1, y: c.y - .1 }));
  if (gorge && route.water) carveRivers(T, route.water, pos, x0, z0, x1, z1, nx, nz, W + 2 * 2.5);
  tg.setAttribute('color', new THREE.BufferAttribute(cols, 3)); tg.computeVertexNormals();
  grp.add(new THREE.Mesh(tg, landMaterial(T, W)));
  const ground = groundOf(pos, x0, z0, x1, z1, nx, nz);
  // the lowest ground under a footprint d by w turned by rot: its corners, the middles of its sides and its centre
  const lowest = (x, z, d, w, rot) => {
    const c = Math.cos(rot), sn = Math.sin(rot); let m = Infinity;
    for (const a of [-.5, 0, .5]) for (const b of [-.5, 0, .5]) m = Math.min(m, ground(x + a * d * c + b * w * sn, z - a * d * sn + b * w * c));
    return m;
  };
  // a block goes down to the lowest ground under it, its roof where it was
  const standing = (b, top) => { b.y = Math.min(b.y, lowest(b.x, b.z, b.d, b.w, b.rot) - ROOT_M); b.h = top - b.y; return b; };
  const plain = steppe ? 0x9d9563 : 0x7f8a60; // the ground beyond the scenery's, to the horizon
  const under = new THREE.Mesh(new THREE.PlaneGeometry(160000, 160000), new THREE.MeshLambertMaterial({ color: plain }));
  // under a map's relief, its lowest ground: the plain shows only past the relief's edge
  const rel = mapOf(route).relief;
  under.rotation.x = -Math.PI / 2; under.position.y = rel ? Math.min(T.minY - 30, reliefLow(rel) - 100) : T.minY - 30; grp.add(under);

  // --- дорога, тротуары ---
  // offsets right of the middle, a number or one per point (null: nothing there)
  const ribbon = (off0, off1, dy, mat, uvScale, skip) => {
    const N = T.N, P = new Float32Array(N * 6), U = new Float32Array(N * 4), I = [];
    const o = {}, a0 = typeof off0 === 'function' ? off0 : () => off0, a1 = typeof off1 === 'function' ? off1 : () => off1;
    for (let i = 0; i < N; i++) {
      sampleAt(T, T.D[i], o);
      // a stretch over road drawn before lies a centimetre above it for each one under it, so the two never flicker
      const y = o.y + dy + .01 * T.over[i], f0 = a0(i), f1 = a1(i);
      P.set([o.x + o.rx * f0, y, o.z + o.rz * f0, o.x + o.rx * f1, y, o.z + o.rz * f1], i * 6);
      U.set([0, T.D[i] / uvScale, 1, T.D[i] / uvScale], i * 4);
      if (i < N - 1 && !(T.again[i] && T.again[i + 1]) && !(skip && (skip(i) || skip(i + 1)))) { const a = i * 2; I.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
    }
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(P, 3)); g.setAttribute('uv', new THREE.BufferAttribute(U, 2)); g.setIndex(I); g.computeVertexNormals();
    const m = new THREE.Mesh(g, mat); grp.add(m); return m;
  };
  const rtex = roadTexture(route.lanes, route.oneway); rtex.wrapS = THREE.ClampToEdgeWrapping; rtex.wrapT = THREE.RepeatWrapping;
  const roadMat = new THREE.MeshLambertMaterial({ map: rtex });
  // where the route turns back on its road, it is drawn as the road going on past the turn (addOnwardRoads), not as
  // the route's own line, which leaves the road's middle for the rider's lane there
  const onward = (route.roads || []).filter(r => r.onward), covered = onwardCover(T, onward, W), onOnward = i => covered[i] === 1;
  ribbon(-W / 2, W / 2, .06, roadMat, 9, onOnward);
  // what lies beside the road on each side: as wide as the land the route leaves -- half the strip between a dual
  // carriageway's two halves -- broken where a road round it meets it
  const room = roomBeside(T, W), onRoad = roadsNear(T, route.roads), o2 = {};
  const sideOf = (k, wide) => i => clamp(room[k][i] / 2, 0, wide);
  // none where the land between is under a metre, where a road meets the route, or over another stretch's road
  const mouth = (k, wide) => i => {
    sampleAt(T, T.D[i], o2); const off = (k ? 1 : -1) * (W / 2 + sideOf(k, wide)(i) * .5), x = o2.x + o2.rx * off, z = o2.z + o2.rz * off;
    return onOnward(i) || room[k][i] < 1 || onRoad(x, z, 0) || routeGap(T, x, z) < W / 2 - .1;
  };
  // a city's pavements, else gravel: beside the route's road and the road going on past its turns
  const town = !gorge && !steppe, sideWide = town ? 5 : 2.5, sideLift = town ? .18 : .02;
  const sideMat = new THREE.MeshLambertMaterial({ color: town ? 0xa7a59c : 0x8b8574 });
  ribbon(i => -W / 2 - sideOf(0, sideWide)(i), -W / 2, sideLift, sideMat, 1, mouth(0, sideWide));
  ribbon(W / 2, i => W / 2 + sideOf(1, sideWide)(i), sideLift, sideMat, 1, mouth(1, sideWide));
  addMedianBarriers(grp, T, W, room);
  // a turning circle where the road ends: its asphalt over the road ridden round it, which there crosses itself
  turningCircles(T, route).forEach(c => {
    const g = new THREE.CircleGeometry(c.r, 48); g.rotateX(-Math.PI / 2);
    const m = new THREE.Mesh(g, circleMat()); m.position.set(c.x, c.y + .1, c.z); m.name = 'turning circle'; grp.add(m);
  });
  // none where a sight is the land (a dam climbed in hairpins): a plain slope with the road on it, as in life
  if (gorge) addFills(grp, T, W, ground, (x, z) => onRoad(x, z, 0) || shapes.some(f => f(x, z) != null), onOnward, (k, i) => mouth(k, sideWide)(i) ? 0 : sideOf(k, sideWide)(i));
  // the roads round the route, what crosses over it and under it, its own bridges and tunnels, lines and water
  // a bridge over the route first: the roads that lead to it climb onto its deck
  const decks = route.over ? overDecks(T, W, route.over) : [];
  if (route.roads) addRoads(grp, T, W, route.roads.filter(r => !r.onward), ground, decks);
  if (onward.length) addOnwardRoads(grp, T, W, onward, ground, roadMat);
  if (decks.length) addOverpasses(grp, T, W, decks, ground);
  if (route.under) addUnderpasses(grp, T, W, route.under, ground);
  if (route.bridges || route.tunnels) addRouteStructures(grp, T, W, ground);
  if (route.lines) addLines(grp, T, route.lines, ground);
  if (route.water) addWater(grp, T, route.water, ground);

  // --- здания ---
  const bl = [];
  const osmB = route.osm ? prepOSM(route.osm.buildings) : route.buildings ? routeBuildings(route, T) : null;
  const tooClose = (x, z, rad) => routeGap(T, x, z) < rad || lms.some(l => Math.hypot(l.x - x, l.z - z) < l.r + rad * .5) || (osmB ? osmB.hit(x, z) : false) || onRoad(x, z, 1.5);
  // «окна» в застройке, чтобы достопримечательности было видно с дороги
  const inView = (s, side) => lms.some(l => { if (l.dist > 700 || (l.side === 'right' ? 1 : -1) !== side) return false; let d = Math.abs(s - l.s); if (T.loop) d = Math.min(d, T.L - d); return d < l.r + 60 + l.dist * .25; });
  if (osmB) { world_osmKept = addOSMBuildings(grp, T, W, lms, osmB, ground); }
  else if (steppe) { /* the steppe has no houses */ }
  else if (!gorge) {
    for (const side of [-1, 1]) for (const row of [0, 1]) {
      let s = r() * 20;
      while (s < T.L) {
        const o = sampleAt(T, s, {}), w = 14 + r() * 18, d = 12 + r() * 12;
        const off = W / 2 + 14 + r() * 18 + row * 46;
        const x = o.x + o.rx * off * side, z = o.z + o.rz * off * side;
        const roll = r(); let h = roll < .7 ? 15 + r() * 12 : roll < .9 ? 30 + r() * 18 : 50 + r() * 45;
        if (row === 1) h *= 1.15;
        if (!inView(s, side) && !tooClose(x, z, W / 2 + 6 + Math.max(w, d) * .55)) bl.push(standing({ x, z, y: o.y - 2, w, d, rot: Math.atan2(o.tx, o.tz), c: r() }, o.y + h));
        s += w + 6 + r() * 16;
      }
    }
  } else {
    let s = 120;
    while (s < 4200) { const o = sampleAt(T, s, {}), side = r() < .5 ? -1 : 1, off = W / 2 + 18 + r() * 40, x = o.x + o.rx * off * side, z = o.z + o.rz * off * side, w = 10 + r() * 10, d = 9 + r() * 8;
      if (!tooClose(x, z, W / 2 + 5 + w * .6)) { const y = terrainH(T, x, z) - 2, h = 8 + r() * 9; bl.push(standing({ x, z, y, w, d, rot: Math.atan2(o.tx, o.tz), c: r() }, y + h)); }
      s += 30 + r() * 70; }
  }
  if (bl.length) {
    const facades = [0xd8cfbf, 0xc9c2b5, 0xe2dccd, 0xb9b5ad, 0xd6c4a8, 0xc7cdd1, 0xe8e3d8, 0xb7a993];
    const bg = new THREE.BoxGeometry(1, 1, 1); bg.translate(0, .5, 0);
    const im = new THREE.InstancedMesh(bg, buildingMat, bl.length), M = new THREE.Matrix4(), Q = new THREE.Quaternion(), S = new THREE.Vector3(), Pv = new THREE.Vector3(), up = new THREE.Vector3(0, 1, 0), col = new THREE.Color();
    bl.forEach((b, i) => { Q.setFromAxisAngle(up, b.rot); S.set(b.d, b.h, b.w); Pv.set(b.x, b.y, b.z); M.compose(Pv, Q, S); im.setMatrixAt(i, M); col.setHex(facades[Math.floor(b.c * facades.length)]); im.setColorAt(i, col); });
    im.frustumCulled = false; im.name = 'houses'; grp.add(im);
  }

  // --- деревья: тополя в городе, тянь-шаньские ели в ущелье, редкие карагачи в степи ---
  // each stands on the ground as drawn, its trunk a little way into it
  const trees = [];
  // where OpenStreetMap maps them -- a gorge's too once its woods carry their leaves (the Cosmostation's); Medeu's,
  // without, has its Tian Shan spruces at random
  if (route.trees && (!gorge || route.trees.firs)) plantOwnTrees(T, route.trees, r, tooClose, ground, W, trees);
  else if (steppe) {
    // along the road a tree now and then, in ones, twos and threes, beyond the shoulder; and a few alone in the grass
    if (!track) for (const side of [-1, 1]) {
      let s = r() * 40;
      while (s < T.L) {
        const n = r() < .55 ? 1 + Math.floor(r() * 3) : 0;
        for (let k = 0; k < n; k++) {
          const at = s + k * (6 + r() * 4), o = sampleAt(T, at, {}), off = W / 2 + 5 + r() * 3.5, x = o.x + o.rx * off * side, z = o.z + o.rz * off * side;
          if (at < T.L && !againAt(at) && !tooClose(x, z, W / 2 + 4)) trees.push({ x, z, y: ground(x, z) - ROOT_M, k: r() < .75 ? 'd' : 'p', s: .7 + r() * .5 });
        }
        s += 18 + r() * 70;
      }
    }
    for (let i = 0; i < 120; i++) { const s = r() * T.L, o = sampleAt(T, s, {}), side = r() < .5 ? -1 : 1, off = W / 2 + 60 + r() * 700, x = o.x + o.rx * off * side, z = o.z + o.rz * off * side; if (r() < .35 && !againAt(s) && !tooClose(x, z, W / 2 + 30)) trees.push({ x, z, y: ground(x, z) - ROOT_M, k: 'd', s: .8 + r() * .5 }); }
  } else if (!gorge) {
    for (const side of [-1, 1]) { let s = r() * 6; while (s < T.L) { const o = sampleAt(T, s, {}), off = W / 2 + 6.5 + r() * .8, x = o.x + o.rx * off * side, z = o.z + o.rz * off * side; if (!againAt(s) && !tooClose(x, z, W / 2 + 4)) trees.push({ x, z, y: ground(x, z) - ROOT_M, k: 'p', s: .85 + r() * .4 }); s += 7 + r() * 4; } }
    for (let i = 0; i < 1400; i++) { const s = r() * T.L, o = sampleAt(T, s, {}), side = r() < .5 ? -1 : 1, off = W / 2 + 40 + r() * 600, x = o.x + o.rx * off * side, z = o.z + o.rz * off * side; if (!tooClose(x, z, W / 2 + 30)) trees.push({ x, z, y: ground(x, z) - ROOT_M, k: r() < .5 ? 'p' : 'd', s: .7 + r() * .5 }); }
  } else {
    for (let i = 0; i < 5200; i++) { const s = r() * T.L, o = sampleAt(T, s, {}), side = r() < .5 ? -1 : 1, off = W / 2 + 7 + Math.pow(r(), 1.6) * 650, x = o.x + o.rx * off * side, z = o.z + o.rz * off * side; const h = ground(x, z); if (h > 2700 || tooClose(x, z, W / 2 + 5)) continue; trees.push({ x, z, y: h - ROOT_M, k: s < 2500 && r() < .6 ? 'd' : 's', s: .7 + r() * .7 }); }
  }
  addTrees(grp, trees);
  if (route.barriers) addBarriers(grp, T, W, route.barriers.gap, ground, (x, z) => !!osmB && osmB.near(x, z, 2));
  if (route.signals) addSignals(grp, T, W, route.signals, ground);
  if (route.rails) addRails(grp, T, W, route.rails, ground, (x, z) => onRoad(x, z, 0));

  // --- the land beyond the scenery: the map's relief as it is, else a range to the south where a route or map has one ---
  const range = route.mountains || mapOf(route).mountains;
  if (rel) addRelief(grp, T, rel, plain, x0, x1, z0, z1); else if (range) addMountains(grp, T, range.south, plain);
  // --- ориентиры ---
  // the land as drawn: the scenery's ground, and past its edge the map's relief
  const land = (x, z) => x > x0 && x < x1 && z > z0 && z < z1 ? ground(x, z) : (reliefAt(T, x, z) ?? terrainH(T, x, z));
  lms.forEach(lm => addLandmark(grp, lm, T, ground, land));
  // --- старт и финиш ---
  if (T.loop || course.back) addArch(grp, T, S0 + 8, t('arch.both'), W); else { addArch(grp, T, S0 + 8, t('arch.start'), W); addArch(grp, T, FIN, t('arch.finish'), W); }

  scene.add(grp); scenery = grp;
  world = course; // only once its scenery stands: a build that failed half way leaves nothing to ride
  return world;
}
// a route's own trees, as OpenStreetMap maps them: rows along the fields' edges, a tree about every 7 m, woods, one
// tree to about 90 square metres, and trees alone; none on the road's shoulder (a racetrack's: none on its run-off,
// 30 m) and none past 1.5 km from it -- the ground is drawn 1.6 km beyond the route, and a tree further out would
// hang over the plain. A wood's leaves say its trees: firs spruces, broad and the rest broadleaved, mixed half and
// half -- in a gorge one whose leaves OpenStreetMap does not give has spruces in the spruce belt, FIRS_FROM_M to
// TREES_TO_M, broadleaved under it and none over it. Its woods hold OWN_TREES at most between them, thinned evenly.
const FIRS_FROM_M = 1500, TREES_TO_M = 2700, OWN_TREES = 25000;
function plantOwnTrees(T, own, r, tooClose, ground, W, trees) {
  const at = p => proj(p[0], p[1], T.origin), clear = T.route.scenery === 'racetrack' ? 30 : 4, gorge = T.route.scenery === 'gorge';
  const broad = () => r() < .75 ? 'd' : 'p';
  const add = (x, z, kind = broad) => {
    if (routeGap(T, x, z) >= 1500 || tooClose(x, z, W / 2 + clear)) return;
    const y = ground(x, z), k = kind(y);
    if (k) trees.push({ x, z, y: y - ROOT_M, k, s: .7 + r() * .5 });
  };
  (own.pts || []).forEach(p => { const q = at(p); add(q.x, q.z); });
  (own.rows || []).forEach(row => {
    const q = row.map(at);
    for (let i = 0; i + 1 < q.length; i++) {
      const a = q[i], b = q[i + 1], L = Math.hypot(b.x - a.x, b.z - a.z);
      for (let s = r() * 4; s < L; s += 5 + r() * 4) add(a.x + (b.x - a.x) * s / L, a.z + (b.z - a.z) * s / L);
    }
  });
  const kinds = {
    woods: gorge ? y => y > TREES_TO_M ? null : y > FIRS_FROM_M ? 's' : broad() : broad,
    firs: () => 's', broad, mixed: () => r() < .5 ? 's' : broad()
  };
  const woods = Object.keys(kinds).flatMap(key => (own[key] || []).map(wood => {
    const ring = wood.map(at).map(p => [p.x, p.z]);
    let area = 0; ring.forEach((p, i) => { const n = ring[(i + 1) % ring.length]; area += p[0] * n[1] - n[0] * p[1]; });
    return { ring, kind: kinds[key], want: Math.min(1500, Math.round(Math.abs(area) / 2 / 90)) };
  }));
  const thin = Math.min(1, OWN_TREES / Math.max(1, woods.reduce((a, w) => a + w.want, 0)));
  woods.forEach(({ ring, kind, want }) => {
    const xs = ring.map(p => p[0]), zs = ring.map(p => p[1]), x0 = Math.min(...xs), x1 = Math.max(...xs), z0 = Math.min(...zs), z1 = Math.max(...zs);
    want = thin < 1 ? Math.floor(want * thin + r()) : want; // a small wood keeps a tree now and then, not none at all
    for (let k = 0, put = 0; put < want && k < want * 6; k++) {
      const x = x0 + r() * (x1 - x0), z = z0 + r() * (z1 - z0);
      if (insideRing(ring, x, z)) { add(x, z, kind); put++; }
    }
  });
}
// A route's turning circles (turn_on_road.py's "circles", [[lat, lon, radius]]): each at its road's height, a ring
// round it for the land to sink under
function turningCircles(T, route) {
  return (route.circles || []).map(([lat, lon, r]) => {
    const c = xzOf(T, [lat, lon]);
    return { x: c.x, z: c.z, r, y: routeNearest(T, c.x, c.z).y, ring: Array.from({ length: 24 }, (_, k) => [c.x + Math.cos(k / 24 * Math.PI * 2) * r, c.z + Math.sin(k / 24 * Math.PI * 2) * r]) };
  });
}
// asphalt without lines, as the road's, a tile every 8 m
let world_circleMat = null;
function circleMat() {
  if (world_circleMat) return world_circleMat;
  const tex = canvasTex(256, 256, (g, w, h) => {
    g.fillStyle = '#3a3c3f'; g.fillRect(0, 0, w, h);
    const r = rng(7); for (let i = 0; i < 2600; i++) { const c = 40 + r() * 40 | 0; g.fillStyle = 'rgba(' + c + ',' + c + ',' + (c + 3) + ',.55)'; g.fillRect(r() * w, r() * h, 1 + r() * 2, 1 + r() * 2); }
  });
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping; tex.repeat.set(4, 4);
  return (world_circleMat = new THREE.MeshLambertMaterial({ map: tex }));
}
// A gorge's road on its slope: where the land beside it lies under its shoulder, a slope falls from the shoulder's edge
// at FILL_SLOPE to one down to the land -- the land's cells, 40 m across, cannot follow a road's shelf, and its road
// hung over the slope by up to 30 m on the Cosmostation. Toward another stretch of road it comes down to that one's
// slope, or to its edge at its height: ended half way, a serpentine's fill hung over the stretch below like a roof.
// One that meets nothing within FILL_MAX_M ends on the land there. Grass as the slopes round it, earth at the road's
// edge -- a fill of earth, as big as the land's own slopes, stood out as a wall. None on a bridge or at a road meeting it.
const FILL_SLOPE = 1.5, FILL_MAX_M = 80, FILL_FROM_M = .4;
function addFills(grp, T, W, ground, onRoad, onOnward, shoulder) {
  const P = [], I = [], C = [], o = {}, bridges = (T.route.bridges || []).map(([a, b]) => [T.ptS[a] - 8, T.ptS[b] + 8]);
  // the land's slope near a road, earthier at the road's edge, stony and snowy with the height as the land round it
  const slope = new THREE.Color(0x3c5536).lerp(new THREE.Color(0x7c8a58), .6), earth = new THREE.Color(0x7d7a5c), rock = new THREE.Color(0x837a6c), snow = new THREE.Color(0xeef2f5), c = new THREE.Color();
  const fillColour = (y, edge) => {
    c.copy(slope).lerp(earth, edge ? .45 : 0).lerp(rock, clamp((y - ROCK_FROM_M) / (ROCK_WHOLE_M - ROCK_FROM_M), 0, 1)).lerp(snow, clamp((y - SNOW_FROM_M) / (SNOW_WHOLE_M - SNOW_FROM_M), 0, 1));
    return [c.r, c.g, c.b];
  };
  for (const k of [0, 1]) {
    const side = k ? 1 : -1;
    let prev = null;
    for (let i = 0; i < T.N; i++) {
      const s = T.D[i];
      sampleAt(T, s, o);
      // from the shoulder's edge, where one is drawn, at its height: from the road's it hung in the air, a guardrail on it
      const from = W / 2 + shoulder(k, i), top = o.y;
      let fill = null;
      const at = d => ({ x: o.x + o.rx * d * side, z: o.z + o.rz * d * side }), a = at(from), first = at(from + 2);
      if (!onOnward(i) && !onRoad(a.x, a.z) && !bridges.some(([p, q]) => s >= p && s <= q)) {
        // where the land 2 m out lies under the fill's slope: right at the edge it may still be up to the road
        if (ground(first.x, first.z) < top - 2 / FILL_SLOPE - FILL_FROM_M) {
          let end = null;
          // out to the land; past the middle to another stretch, to its slope, or to its edge at its height -- a road
          // ridden out and back is its own neighbour, which roomBeside counts: not here
          for (let d = from + 1; d <= from + FILL_MAX_M && !end; d += 1) {
            const q = at(d), y = top - (d - from) / FILL_SLOPE, g = ground(q.x, q.z), gap = routeGap(T, q.x, q.z);
            if (g >= y) end = { x: q.x, y: g, z: q.z };
            else if (gap < d - 1) {
              const n = routeNearest(T, q.x, q.z), theirs = n.y - .05 - Math.max(0, gap - W / 2) / FILL_SLOPE;
              if (gap <= W / 2) end = { x: q.x, y: Math.min(y, n.y - .05), z: q.z };
              else if (theirs >= y) end = { x: q.x, y, z: q.z };
            }
            if (!end && d + 1 > from + FILL_MAX_M) end = { x: q.x, y: g, z: q.z };
          }
          fill = [a.x, top, a.z, end.x, end.y, end.z];
        }
      }
      if (fill && prev) { const b = P.length / 3; P.push(...prev, ...fill); I.push(b, b + 1, b + 3, b, b + 3, b + 2); [[prev[1], 1], [prev[4], 0], [fill[1], 1], [fill[4], 0]].forEach(([y, edge]) => C.push(...fillColour(y, edge))); }
      prev = fill;
    }
  }
  const m = meshOf(grp, P, I, new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide }), 'fills');
  if (m) m.geometry.setAttribute('color', new THREE.Float32BufferAttribute(C, 3));
}
// A mountain road's guardrail from rails.from to rails.to (each [latitude, longitude], on the route's first pass), on
// a side whose land falls away RAIL_DROP_M within RAIL_LOOK_M of its edge: a beam in black and white on posts on the
// shoulder; and at a turn tighter than RAIL_TURN_DEG in 40 m, red and white chevrons on its outside, one to the riders
// coming each way -- the road from Big Almaty Lake up to the Cosmostation, as the maintainer's photograph has it
const RAIL_DROP_M = 2.5, RAIL_LOOK_M = 6, RAIL_OFF_M = .7, RAIL_POST_M = 4, RAIL_TURN_DEG = 100;
function addRails(grp, T, W, rails, ground, onRoad) {
  const firstPass = p => { const q = proj(p[0], p[1], T.origin); return T.D[firstPassAt(T, q.x, q.z)]; };
  const s0 = firstPass(rails.from), s1 = firstPass(rails.to), o = {};
  const stripes = canvasTex(256, 32, (c, w, h) => { c.fillStyle = '#f2f2ee'; c.fillRect(0, 0, w, h); c.fillStyle = '#1d1f22'; c.fillRect(w / 2, 0, w / 2, h); });
  stripes.wrapS = THREE.RepeatWrapping;
  const P = [], UV = [], I = [], posts = [];
  for (const side of [-1, 1]) {
    let prev = null;
    for (let s = s0, k = 0; s <= s1; s += 2, k++) {
      sampleAt(T, s, o);
      const at = d => ({ x: o.x + o.rx * d * side, z: o.z + o.rz * d * side }), q = at(W / 2 + RAIL_LOOK_M), e = at(W / 2 + RAIL_OFF_M);
      // none across a road meeting the route there: the Panorama's car park was railed off
      const steep = ground(q.x, q.z) < o.y - RAIL_DROP_M && !onRoad(e.x, e.z) && !onRoad(q.x, q.z);
      if (!steep) { prev = null; continue; }
      const cur = [e.x, o.y, e.z, s];
      if (prev) {
        const b = P.length / 3;
        P.push(prev[0], prev[1] + .6, prev[2], prev[0], prev[1] + .92, prev[2], cur[0], cur[1] + .6, cur[2], cur[0], cur[1] + .92, cur[2]);
        UV.push(prev[3] / 2, 0, prev[3] / 2, 1, s / 2, 0, s / 2, 1);
        I.push(b, b + 2, b + 1, b + 1, b + 2, b + 3);
      }
      if (k % (RAIL_POST_M / 2) === 0) posts.push({ x: e.x, y: o.y, z: e.z }); // a post every RAIL_POST_M: by the step's count -- by the metre, a start on an odd one had none
      prev = cur;
    }
  }
  if (I.length) {
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(P, 3)); g.setAttribute('uv', new THREE.Float32BufferAttribute(UV, 2)); g.setIndex(I); g.computeVertexNormals();
    const m = new THREE.Mesh(g, new THREE.MeshLambertMaterial({ map: stripes, side: THREE.DoubleSide })); m.name = 'rails'; grp.add(m);
  }
  if (posts.length) {
    const im = new THREE.InstancedMesh(new THREE.BoxGeometry(.12, 1, .12), new THREE.MeshLambertMaterial({ color: 0x8d9296 }), posts.length), M = new THREE.Matrix4();
    posts.forEach((p, i) => { M.makeTranslation(p.x, p.y + .35, p.z); im.setMatrixAt(i, M); });
    im.name = 'railPosts'; grp.add(im);
  }
  // chevrons on the outside of the tight turns, a board to the riders coming each way
  const chev = canvasTex(256, 96, (c, w, h) => {
    c.fillStyle = '#d23a2f'; c.fillRect(0, 0, w, h); c.fillStyle = '#ffffff';
    for (let k = 0; k < 3; k++) { const x = 40 + k * 72; c.beginPath(); c.moveTo(x, 10); c.lineTo(x + 34, h / 2); c.lineTo(x, h - 10); c.lineTo(x + 18, h - 10); c.lineTo(x + 52, h / 2); c.lineTo(x + 18, 10); c.fill(); }
  });
  const a = {}, b = {}, way = (p, q) => Math.atan2(q.x - p.x, q.z - p.z);
  let last = -Infinity;
  for (let s = s0 + 20; s <= s1 - 20; s += 4) {
    sampleAt(T, s - 20, a); sampleAt(T, s + 20, b); sampleAt(T, s, o);
    const turn = ((Math.atan2(b.tx, b.tz) - Math.atan2(a.tx, a.tz) + 3 * Math.PI) % (2 * Math.PI)) - Math.PI;
    if (Math.abs(turn) * 180 / Math.PI < RAIL_TURN_DEG || s - last < 60) continue;
    last = s;
    // a growing heading turns left (from facing +z to +x): its outside is on the right
    const out = turn > 0 ? 1 : -1, x = o.x + o.rx * (W / 2 + 1.2) * out, z = o.z + o.rz * (W / 2 + 1.2) * out;
    [[a, turn > 0], [b, turn < 0]].forEach(([from, left]) => {
      const grey = new THREE.MeshLambertMaterial({ color: 0x9aa0a6 });
      const board = new THREE.Mesh(new THREE.BoxGeometry(1.6, .6, .05), [grey, grey, grey, grey, new THREE.MeshBasicMaterial({ map: chev }), grey]);
      // its front to the riders coming from there, its arrows the way the road bends for them
      board.position.set(x, o.y + 1.5, z); board.rotation.order = 'YXZ'; board.rotation.y = way({ x, z }, from); board.rotation.z = left ? Math.PI : 0;
      grp.add(board);
    });
    const post = new THREE.Mesh(new THREE.BoxGeometry(.08, 1.6, .08), new THREE.MeshLambertMaterial({ color: 0x8d9296 })); post.position.set(x, o.y + .6, z); grp.add(post);
  }
}
// Traffic lights where the route's road has them: a pole each side beyond the edge, its lights turned to the riders
// coming on that side -- a ride's lights always green
const SIGNAL_POLE_M = 4.2;
function addSignals(grp, T, W, list, ground) {
  const pole = new THREE.MeshLambertMaterial({ color: 0x55595e }), dark = new THREE.MeshLambertMaterial({ color: 0x24272a });
  const lens = [0x3a1512, 0x3a3112, null].map(c => c == null ? new THREE.MeshBasicMaterial({ color: 0x3dff6e }) : new THREE.MeshLambertMaterial({ color: c }));
  const o = {};
  list.forEach(p => {
    const q = proj(p[0], p[1], T.origin), n = routeNearest(T, q.x, q.z);
    sampleAt(T, n.s, o);
    [-1, 1].forEach(side => {
      const g = new THREE.Group(), x = o.x + o.rx * (W / 2 + 1.2) * side, z = o.z + o.rz * (W / 2 + 1.2) * side, y = ground(x, z);
      const post = new THREE.Mesh(new THREE.CylinderGeometry(.08, .1, SIGNAL_POLE_M + .5, 8), pole); post.position.y = (SIGNAL_POLE_M - .5) / 2; g.add(post);
      const head = new THREE.Mesh(new THREE.BoxGeometry(.4, 1.1, .3), dark); head.position.y = SIGNAL_POLE_M - .1; g.add(head);
      lens.forEach((m, k) => { const l = new THREE.Mesh(new THREE.CircleGeometry(.12, 12), m); l.position.set(0, SIGNAL_POLE_M + .25 - k * .35, .16); g.add(l); });
      // the riders on the right side of the road come along it, those on the left against it: the lights face them
      g.position.set(x, y, z); g.rotation.y = Math.atan2(-o.tx * side, -o.tz * side); grp.add(g);
    });
  });
}
// A racetrack's guardrail along both edges, gap metres beyond the road, and its catch fence of mesh on posts a metre
// behind it: broken where a building stands, and where the line would come nearer another stretch of the track than
// its own -- inside a hairpin tighter than the gap
function addBarriers(grp, T, W, gap, ground, building) {
  const STEP = 2, o = {}, rail = [], mesh = [], posts = [];
  const line = (off, side, out, postEvery) => {
    let prev = null;
    for (let s = 0, i = 0; s <= T.L; s += STEP, i++) {
      sampleAt(T, s, o);
      const x = o.x + o.rx * off * side, z = o.z + o.rz * off * side;
      if (building(x, z) || routeGap(T, x, z) < off - 1) { prev = null; continue; }
      const p = { x, z, y: ground(x, z) };
      if (prev) out.push(prev, p);
      if (postEvery && i % postEvery === 0) posts.push(p);
      prev = p;
    }
  };
  for (const side of [-1, 1]) { line(W / 2 + gap, side, rail, 0); line(W / 2 + gap + 1, side, mesh, 3); }
  const strip = (pairs, y0, y1, mat, name) => { // a band standing on the ground between y0 and y1 above it
    if (!pairs.length) return;
    const P = new Float32Array(pairs.length * 9);
    for (let i = 0; i < pairs.length; i += 2) {
      const a = pairs[i], b = pairs[i + 1];
      P.set([a.x, a.y + y0, a.z, b.x, b.y + y0, b.z, b.x, b.y + y1, b.z, a.x, a.y + y0, a.z, b.x, b.y + y1, b.z, a.x, a.y + y1, a.z], i * 9);
    }
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(P, 3)); g.computeVertexNormals();
    const m = new THREE.Mesh(g, mat); m.name = name; grp.add(m);
  };
  strip(rail, .45, .8, new THREE.MeshLambertMaterial({ color: 0xc3c8cc, side: THREE.DoubleSide }), 'rail');
  strip(mesh, 0, 3.6, new THREE.MeshLambertMaterial({ color: 0x7d838a, side: THREE.DoubleSide, transparent: true, opacity: .25, depthWrite: false }), 'fence');
  if (!posts.length) return;
  const bg = new THREE.BoxGeometry(1, 1, 1); bg.translate(0, .5, 0);
  const im = new THREE.InstancedMesh(bg, new THREE.MeshLambertMaterial({ color: 0x5b6066 }), posts.length), M = new THREE.Matrix4();
  posts.forEach((p, i) => im.setMatrixAt(i, M.makeScale(.1, 4.2, .1).setPosition(p.x, p.y - ROOT_M, p.z)));
  im.name = 'posts'; grp.add(im);
}
function addTrees(grp, list) {
  const kinds = { p: [], d: [], s: [] }; list.forEach(t => kinds[t.k].push(t));
  const M = new THREE.Matrix4(), Q = new THREE.Quaternion(), S = new THREE.Vector3(), P = new THREE.Vector3(), col = new THREE.Color();
  const trunkG = new THREE.CylinderGeometry(.18, .28, 1, 5); trunkG.translate(0, .5, 0);
  const all = list.length; if (!all) return;
  const trunks = new THREE.InstancedMesh(trunkG, new THREE.MeshLambertMaterial({ color: 0x5a4a3a }), all); let ti = 0;
  trunks.name = 'trunks';
  const crowns = (geo, arr, f) => { if (!arr.length) return; const im = new THREE.InstancedMesh(geo, treeMat, arr.length); arr.forEach((t, i) => { f(t, i, im); M.makeTranslation(t.x, t.y, t.z); M.scale(S.set(1, t.s * (t.k === 's' ? 2.2 : 3), 1)); trunks.setMatrixAt(ti++, M); }); im.frustumCulled = false; grp.add(im); };
  const pG = new THREE.SphereGeometry(1, 8, 6); pG.translate(0, 1, 0);
  crowns(pG, kinds.p, (t, i, im) => { P.set(t.x, t.y + 2.2 * t.s, t.z); S.set(1.7 * t.s, 8.5 * t.s, 1.7 * t.s); M.compose(P, Q.identity(), S); im.setMatrixAt(i, M); col.setHSL(.24 + Math.random() * .04, .35, .27 + Math.random() * .08); im.setColorAt(i, col); });
  const dG = new THREE.IcosahedronGeometry(1, 0); dG.translate(0, 1, 0);
  crowns(dG, kinds.d, (t, i, im) => { P.set(t.x, t.y + 2 * t.s, t.z); S.set(3.4 * t.s, 3 * t.s, 3.4 * t.s); M.compose(P, Q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), Math.random() * 6), S); im.setMatrixAt(i, M); col.setHSL(.2 + Math.random() * .08, .4, .3 + Math.random() * .1); im.setColorAt(i, col); });
  const sG = new THREE.ConeGeometry(1, 1, 7); sG.translate(0, .5, 0);
  crowns(sG, kinds.s, (t, i, im) => { P.set(t.x, t.y + 1.2 * t.s, t.z); S.set(2.6 * t.s, 15 * t.s, 2.6 * t.s); M.compose(P, Q.identity(), S); im.setMatrixAt(i, M); col.setHSL(.38 + Math.random() * .05, .3, .17 + Math.random() * .06); im.setColorAt(i, col); });
  trunks.count = ti; trunks.frustumCulled = false; grp.add(trunks);
}
// A range farther than this from the origin rises from the plain over the rest of the way, and is seen through a
// quarter of the haze beyond it: the scene's haze is there to hide where the ground ends near the road, and would
// hide a far range whole, which real air shows for a hundred kilometres. A range this near keeps the scene's haze.
const RANGE_CLEAR_M = 9500, RANGE_HAZE = .25;
// A range runs 150 km either way from the origin, so it never ends in view: 90 km in all ended 45 km to the east of
// Kyrbaltabay's, inside the view on the way back towards it, where the real range goes on; 400 columns keep its
// ridges about 750 m apart.
const RANGE_WIDE_M = 300000, RANGE_COLUMNS = 400;
function addMountains(grp, T, south, plain) {
  const near = T.maxZ + 2600, zStart = Math.max(near, south), ramp = Math.max(0, zStart - Math.max(RANGE_CLEAR_M, near)), W = RANGE_WIDE_M, D = 36000 + ramp;
  const g = new THREE.PlaneGeometry(W, D, RANGE_COLUMNS, 90 + Math.ceil(ramp / 400)); g.rotateX(-Math.PI / 2); g.translate(0, 0, zStart - ramp + D / 2 - 800);
  const p = g.attributes.position, cols = new Float32Array(p.count * 3), c = new THREE.Color(), forest = new THREE.Color(0x40563a), rock = new THREE.Color(0x7d766c), snow = new THREE.Color(0xf3f6f8), low = new THREE.Color(plain);
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i), z = Math.max(p.getZ(i), zStart - 800), dz = z - zStart; // on the rise to the foot, the foot's height
    const ridge = clamp(dz / 7000, 0, 1), ridge2 = Math.exp(-Math.pow((dz - 14000) / 9000, 2));
    const n = fbm(x * .00018, z * .00018, 5), m = 1 - Math.abs(fbm(x * .0004 + 3, z * .0004, 4) * 2 - 1);
    let h = 900 + ridge * 900 + ridge2 * (1700 + n * 1700 + m * 900) + dz * .02;
    c.copy(forest).lerp(rock, clamp((h - 2300) / 600, 0, 1)); if (h > 3250 + n * 400) c.copy(snow);
    if (p.getZ(i) < z) { const f = clamp((p.getZ(i) - (zStart - 800 - ramp)) / ramp, 0, 1); h = lerp(T.minY - 30, h, f * f); c.lerp(low, 1 - f); }
    p.setY(i, h);
    cols[i * 3] = c.r; cols[i * 3 + 1] = c.g; cols[i * 3 + 2] = c.b;
  }
  g.setAttribute('color', new THREE.BufferAttribute(cols, 3)); g.computeVertexNormals();
  const mat = new THREE.MeshLambertMaterial({ vertexColors: true });
  if (ramp > 0) farHaze(mat);
  const range = new THREE.Mesh(g, mat); range.name = 'range'; grp.add(range);
}
// beyond RANGE_CLEAR_M the land shows through a quarter of the scene's haze
function farHaze(mat) {
  const C = RANGE_CLEAR_M.toFixed(1), k = RANGE_HAZE.toFixed(2);
  mat.onBeforeCompile = sh => {
    sh.fragmentShader = sh.fragmentShader.replace('#include <fog_fragment>', THREE.ShaderChunk.fog_fragment
      .replace('#ifdef FOG_EXP2', '#ifdef FOG_EXP2\n\t\tfloat hazeDepth = fogDepth < ' + C + ' ? fogDepth : ' + C + ' + (fogDepth - ' + C + ') * ' + k + ';')
      .replace('fogDepth * fogDepth', 'hazeDepth * hazeDepth'));
  };
  mat.customProgramCacheKey = () => 'far-range';
}
// A map's relief (js/maps.js): SRTM heights on a grid of latitude and longitude, the real mountains, hills and
// valleys round its routes, laid out from the route's origin and lowered by the Earth's curve as a rider sees it -- a
// peak 100 km off stands about 680 m lower, the air's bending taken off (0.87 of the drop). Over the scenery's own
// ground (x0..x1, z0..z1) it is not drawn: the two meet at that ground's edge, the ground come to the relief's own
// surface there (edgeLand, farReliefAt); beyond RANGE_CLEAR_M it shows through a quarter of the haze.
const EARTH_R = 6371000, REFRACTION = .87, RELIEF_EDGE = 400;
// The scenery's ground within RELIEF_EDGE of its edge comes to the far relief's surface, so the two meet there: the
// finer grids and a gorge's walls are the scenery's alone
function edgeLand(T, x, z, h, x0, x1, z0, z1) {
  const e = Math.min(x - x0, x1 - x, z - z0, z1 - z), far = e < RELIEF_EDGE ? farReliefAt(T, x, z) : null;
  if (far == null) return h;
  const k = clamp(e / RELIEF_EDGE, 0, 1);
  return far + (h - far) * k * k * (3 - 2 * k);
}
const reliefLow = rel => rel.low != null ? rel.low : (rel.low = rel.h.reduce((a, b) => Math.min(a, b), Infinity));
function addRelief(grp, T, rel, plain, x0, x1, z0, z1) {
  const [la0, dla, nr] = rel.lat, [lo0, dlo, nc] = rel.lon, H = rel.h, O = T.origin;
  const P = new Float32Array(nr * nc * 3), cols = new Float32Array(nr * nc * 3), I = [];
  const c = new THREE.Color(), low = new THREE.Color(plain), forest = new THREE.Color(0x40563a), rock = new THREE.Color(0x7d766c), snow = new THREE.Color(0xf3f6f8);
  for (let i = 0; i < nr; i++) for (let j = 0; j < nc; j++) {
    const k = i * nc + j, q = proj(la0 + i * dla, lo0 + j * dlo, O), d = Math.hypot(q.x, q.z), m = H[k];
    const h = m - d * d / (2 * EARTH_R) * REFRACTION; // over the scenery's own ground it is not drawn at all
    const n = fbm(q.x * .0004, q.z * .0004, 3);
    c.copy(low).lerp(forest, clamp((m - 1100) / 500, 0, 1)).lerp(rock, clamp((m - 2300 - n * 300) / 500, 0, 1));
    if (m > 3300 + n * 400) c.copy(snow);
    P[k * 3] = q.x; P[k * 3 + 1] = h; P[k * 3 + 2] = q.z; cols[k * 3] = c.r; cols[k * 3 + 1] = c.g; cols[k * 3 + 2] = c.b;
    if (i + 1 < nr && j + 1 < nc) I.push(k, k + nc, k + 1, k + 1, k + nc, k + nc + 1);
  }
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(P, 3)); g.setAttribute('color', new THREE.BufferAttribute(cols, 3));
  g.setIndex(I); g.computeVertexNormals();
  const mat = new THREE.MeshLambertMaterial({ vertexColors: true }); farHaze(mat);
  // inside the scenery's box its own ground is the land: the relief's facets there, a kilometre across, stood through
  // it where it dips between their corners (Medeu's gorge, by up to 110 m), so they are left out
  const haze = mat.onBeforeCompile, box = new THREE.Vector4(x0, z0, x1, z1);
  mat.onBeforeCompile = sh => {
    haze(sh);
    sh.uniforms.sceneBox = { value: box };
    sh.vertexShader = 'varying vec2 vBoxXZ;\n' + sh.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\n  vBoxXZ = (modelMatrix * vec4(transformed, 1.0)).xz;');
    sh.fragmentShader = 'uniform vec4 sceneBox;\nvarying vec2 vBoxXZ;\n' + sh.fragmentShader.replace('void main() {', 'void main() {\n  if (vBoxXZ.x > sceneBox.x && vBoxXZ.x < sceneBox.z && vBoxXZ.y > sceneBox.y && vBoxXZ.y < sceneBox.w) discard;');
  };
  mat.customProgramCacheKey = () => 'far-range-boxed';
  const relief = new THREE.Mesh(g, mat); relief.name = 'relief'; grp.add(relief);
}
