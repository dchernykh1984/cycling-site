'use strict';
/* ---------------- Мир: рельеф, дорога, здания, деревья, горы, старт и финиш ---------------- */
let scenery = null; // the 3D world drawn along the course being ridden
function disposeWorld() {
  if (!scenery) return;
  scene.remove(scenery);
  scenery.traverse(o => { if (o.geometry) o.geometry.dispose(); [].concat(o.material || []).forEach(m => { if (m === buildingMat || m === treeMat || m === osmMat) return; if (m.map) m.map.dispose(); m.dispose(); }); });
  scenery = null; world = null;
}
function terrainH(T, x, z) {
  const n = nearest(T, x, z); let h = n.y - 1.2;
  if (T.route.scenery === 'gorge') {
    if (n.d > 45) { const k = n.d - 45, f = clamp((n.s - 1200) / 3000, .12, 1); h += f * (k * .46 + fbm(x * .004, z * .004) * Math.min(1, k / 120) * 70); }
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
// how deep a trunk goes into the ground: a slope under it leaves no gap at its foot
const ROOT_M = .3;
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
  const nx = Math.min(260, Math.ceil((x1 - x0) / 40)), nz = Math.min(260, Math.ceil((z1 - z0) / 40));
  const tg = new THREE.PlaneGeometry(x1 - x0, z1 - z0, nx, nz); tg.rotateX(-Math.PI / 2); tg.translate((x0 + x1) / 2, 0, (z0 + z1) / 2);
  const pos = tg.attributes.position, cols = new Float32Array(pos.count * 3);
  const cGrass = new THREE.Color(0x7c8a58), cDust = new THREE.Color(0x9a9684), cForest = new THREE.Color(0x3c5536), cRock = new THREE.Color(0x837a6c), cSnow = new THREE.Color(0xeef2f5), tmp = new THREE.Color();
  const cDry = new THREE.Color(0xa49b67), cMeadow = new THREE.Color(0x8b8e58); // the steppe: dry grass, and greener hollows
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i), z = pos.getZ(i), n = nearest(T, x, z), h = terrainH(T, x, z); pos.setY(i, h);
    const nz2 = fbm(x * .01, z * .01, 3);
    if (gorge) { const rise = h - n.y; tmp.copy(cForest).lerp(cGrass, clamp(1 - n.d / 120, 0, 1) * .6).lerp(cRock, clamp((rise - 250) / 350, 0, 1) * .8 + nz2 * .15); if (h > 2900) tmp.lerp(cSnow, clamp((h - 2900) / 300, 0, 1)); }
    else if (steppe) tmp.copy(cDry).lerp(cMeadow, clamp(fbm(x * .0012, z * .0012, 3) * 1.6 - .45, 0, 1) * .85).lerp(cDust, clamp(1 - (n.d - W) / 30, 0, 1) * .5 + nz2 * .12);
    else tmp.copy(cGrass).lerp(cDust, clamp(1 - (n.d - W) / 60, 0, 1) * .7 + nz2 * .3);
    cols[i * 3] = tmp.r; cols[i * 3 + 1] = tmp.g; cols[i * 3 + 2] = tmp.b;
  }
  tg.setAttribute('color', new THREE.BufferAttribute(cols, 3)); tg.computeVertexNormals();
  grp.add(new THREE.Mesh(tg, new THREE.MeshLambertMaterial({ vertexColors: true })));
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
  under.rotation.x = -Math.PI / 2; under.position.y = T.minY - 30; grp.add(under);

  // --- дорога, тротуары ---
  const ribbon = (off0, off1, dy, mat, uvScale) => {
    const N = T.N, P = new Float32Array(N * 6), U = new Float32Array(N * 4), I = [];
    const o = {};
    for (let i = 0; i < N; i++) {
      sampleAt(T, T.D[i], o);
      // a stretch over road drawn before lies a centimetre above it for each one under it, so the two never flicker
      const y = o.y + dy + .01 * T.over[i];
      P.set([o.x + o.rx * off0, y, o.z + o.rz * off0, o.x + o.rx * off1, y, o.z + o.rz * off1], i * 6);
      U.set([0, T.D[i] / uvScale, 1, T.D[i] / uvScale], i * 4);
      if (i < N - 1 && !(T.again[i] && T.again[i + 1])) { const a = i * 2; I.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
    }
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(P, 3)); g.setAttribute('uv', new THREE.BufferAttribute(U, 2)); g.setIndex(I); g.computeVertexNormals();
    const m = new THREE.Mesh(g, mat); grp.add(m); return m;
  };
  const rtex = roadTexture(route.lanes); rtex.wrapS = THREE.ClampToEdgeWrapping; rtex.wrapT = THREE.RepeatWrapping;
  ribbon(-W / 2, W / 2, .06, new THREE.MeshLambertMaterial({ map: rtex }), 9);
  if (!gorge && !steppe) {
    const walk = new THREE.MeshLambertMaterial({ color: 0xa7a59c });
    ribbon(-W / 2 - 5, -W / 2, .18, walk, 1); ribbon(W / 2, W / 2 + 5, .18, walk, 1);
  } else {
    const grav = new THREE.MeshLambertMaterial({ color: 0x8b8574 });
    ribbon(-W / 2 - 2.5, -W / 2, .02, grav, 1); ribbon(W / 2, W / 2 + 2.5, .02, grav, 1);
  }

  // --- здания ---
  const bl = [];
  const osmB = route.osm ? prepOSM(route.osm.buildings) : null;
  const tooClose = (x, z, rad) => routeGap(T, x, z) < rad || lms.some(l => Math.hypot(l.x - x, l.z - z) < l.r + rad * .5) || (osmB ? osmB.hit(x, z) : false);
  // «окна» в застройке, чтобы достопримечательности было видно с дороги
  const inView = (s, side) => lms.some(l => { if (l.dist > 700 || (l.side === 'right' ? 1 : -1) !== side) return false; let d = Math.abs(s - l.s); if (T.loop) d = Math.min(d, T.L - d); return d < l.r + 60 + l.dist * .25; });
  if (osmB) { world_osmKept = addOSMBuildings(grp, T, W, lms, osmB); }
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
    im.frustumCulled = false; grp.add(im);
  }

  // --- деревья: тополя в городе, тянь-шаньские ели в ущелье, редкие карагачи в степи ---
  // each stands on the ground as drawn, its trunk a little way into it
  const trees = [];
  if (steppe) {
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

  // --- a mountain range to the south, on a route or a map that has one ---
  const range = route.mountains || mapOf(route).mountains; if (range) addMountains(grp, T, range.south, plain);
  // --- ориентиры ---
  lms.forEach(lm => addLandmark(grp, lm, T, ground));
  // --- старт и финиш ---
  if (T.loop || course.back) addArch(grp, T, S0 + 8, t('arch.both'), W); else { addArch(grp, T, S0 + 8, t('arch.start'), W); addArch(grp, T, FIN, t('arch.finish'), W); }

  scene.add(grp); scenery = grp;
  world = course; // only once its scenery stands: a build that failed half way leaves nothing to ride
  return world;
}
function addTrees(grp, list) {
  const kinds = { p: [], d: [], s: [] }; list.forEach(t => kinds[t.k].push(t));
  const M = new THREE.Matrix4(), Q = new THREE.Quaternion(), S = new THREE.Vector3(), P = new THREE.Vector3(), col = new THREE.Color();
  const trunkG = new THREE.CylinderGeometry(.18, .28, 1, 5); trunkG.translate(0, .5, 0);
  const all = list.length; if (!all) return;
  const trunks = new THREE.InstancedMesh(trunkG, new THREE.MeshLambertMaterial({ color: 0x5a4a3a }), all); let ti = 0;
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
function addMountains(grp, T, south, plain) {
  const near = T.maxZ + 2600, zStart = Math.max(near, south), ramp = Math.max(0, zStart - Math.max(RANGE_CLEAR_M, near)), W = 90000, D = 36000 + ramp;
  const g = new THREE.PlaneGeometry(W, D, 220, 90 + Math.ceil(ramp / 400)); g.rotateX(-Math.PI / 2); g.translate(0, 0, zStart - ramp + D / 2 - 800);
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
  if (ramp > 0) {
    const C = RANGE_CLEAR_M.toFixed(1), k = RANGE_HAZE.toFixed(2);
    mat.onBeforeCompile = sh => {
      sh.fragmentShader = sh.fragmentShader.replace('#include <fog_fragment>', THREE.ShaderChunk.fog_fragment
        .replace('#ifdef FOG_EXP2', '#ifdef FOG_EXP2\n\t\tfloat hazeDepth = fogDepth < ' + C + ' ? fogDepth : ' + C + ' + (fogDepth - ' + C + ') * ' + k + ';')
        .replace('fogDepth * fogDepth', 'hazeDepth * hazeDepth'));
    };
    mat.customProgramCacheKey = () => 'far-range';
  }
  grp.add(new THREE.Mesh(g, mat));
}
