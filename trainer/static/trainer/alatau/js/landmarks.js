'use strict';
function addLandmark(grp, lm, q, T) {
  const lam = c => new THREE.MeshLambertMaterial({ color: c });
  const G = new THREE.Group();
  G.position.set(q.x, lm.type === 'tvtower' ? lm.ele : terrainH(T, q.x, q.z) + .4, q.z);
  if (lm.rot != null) G.rotation.y = lm.rot;
  const M = c => typeof c === 'number' ? lam(c) : c;
  const box = (w, h, d, c, x = 0, y = 0, z = 0) => { const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), M(c)); m.position.set(x, y + h / 2, z); G.add(m); return m; };
  const cyl = (r1, r2, h, c, x = 0, y = 0, z = 0, seg = 16) => { const m = new THREE.Mesh(new THREE.CylinderGeometry(r1, r2, h, seg), M(c)); m.position.set(x, y + h / 2, z); G.add(m); return m; };
  const onion = (r, c, x, y, z, spire) => {
    const pts = [[.62, 0], [1, .35], [1.06, .7], [.88, 1.1], [.5, 1.5], [.16, 1.85], [.04, 2.1], [0, 2.15]].map(p => new THREE.Vector2(p[0] * r, p[1] * r));
    const m = new THREE.Mesh(new THREE.LatheGeometry(pts, 16), M(c)); m.position.set(x, y, z); G.add(m);
    if (spire) { cyl(.18, .25, spire, 0xe2b23c, x, y + r * 2.1, z, 6); box(.25, .25, spire * .35, 0xe2b23c, x, y + r * 2.1 + spire * .7, z); }
  };
  switch (lm.type) {
    case 'tvtower': {
      const hill = new THREE.Mesh(new THREE.ConeGeometry(700, 230, 24, 1), lam(0x667a4c)); hill.position.y = -175; G.add(hill);
      const t = new THREE.Mesh(new THREE.CylinderGeometry(1.6, 13, 372, 6, 1, true), new THREE.MeshLambertMaterial({ color: 0xc9ccd0, wireframe: true })); t.position.y = 126; G.add(t);
      [120, 210, 300].forEach(h => cyl(8 - h / 60, 8 - h / 60, 4, 0xe8e8e8, 0, h - 60, 0, 12));
      break;
    }
    case 'glass': { box(34, lm.h, 26, 0x6f8aa2, 0, -2); G.rotation.y = .3; box(30, 6, 22, 0x8aa2b8, 0, lm.h - 2).rotation.z = .12; break; }
    case 'hotel': {
      const m = new THREE.Mesh(new THREE.BoxGeometry(22, lm.h, 40), buildingMat); m.position.y = lm.h / 2 - 2; G.add(m);
      const crown = new THREE.Mesh(new THREE.CylinderGeometry(3, 12, 18, 4), lam(0xd4a648)); crown.position.y = lm.h + 7; G.add(crown);
      break;
    }
    case 'rink': { // каток лежит на дне долины, длинной стороной вдоль ущелья
      const o = sampleAt(T, T.L, {}); G.position.y = nearest(T, q.x, q.z).y - 1; G.rotation.y = Math.atan2(q.x - o.x, q.z - o.z);
      box(130, 6, 190, 0x9aa0a6, 0, -5); box(100, .6, 160, 0xe4f1fb, 0, 1);
      [-1, 1].forEach(k => { const st = new THREE.Mesh(new THREE.BoxGeometry(16, 20, 190), buildingMat); st.position.set(k * 74, 9, 0); G.add(st); });
      break;
    }
    case 'cathedral': { // деревянный собор: пастельные стены, красные крыши, луковичные главы
      const wall = 0xf3e2a6, roof = 0xc96a6a, gold = 0xe2b23c;
      box(22, 16, 44, wall, 0, -1); box(42, 14, 18, wall, 0, -1);
      box(24, 1.6, 46, roof, 0, 15); box(44, 1.6, 20, roof, 0, 13);
      cyl(7, 7, 12, wall, 0, 15, 0, 8); cyl(7.6, 7.6, 1.2, roof, 0, 26.5, 0, 8); onion(7, gold, 0, 27.5, 0, 6);
      [[-9, -9], [9, -9], [-9, 9], [9, 9]].forEach(p => { cyl(2.6, 2.6, 7, wall, p[0], 15, p[1], 8); onion(2.8, roof, p[0], 22, p[1], 3); });
      box(11, 28, 11, wall, 0, -1, -27); box(12, 1.4, 12, roof, 0, 26.5, -27); box(8, 9, 8, wall, 0, 27.5, -27); onion(4, gold, 0, 36.5, -27, 7);
      G.rotation.y = Math.PI / 2;
      break;
    }
    case 'opera': {
      const cream = 0xf0e2c0;
      box(64, 17, 52, cream, 0, -1); box(36, 27, 34, cream, 0, -1); box(40, 1.6, 38, 0xd9cfb6, 0, 26);
      for (let i = 0; i < 8; i++) cyl(1.1, 1.3, 13, 0xfbf8f0, -14 + i * 4, 0, 29, 10);
      box(36, 3.5, 6, 0xfbf8f0, 0, 13, 29); box(32, 2.5, 5, 0xfbf8f0, 0, 16.5, 29).scale.x = .9;
      G.rotation.y = -Math.PI / 2;
      break;
    }
    case 'palace': {
      box(80, 16, 54, 0x34404b, 0, -1);
      box(98, 3, 70, 0xdcdad2, 0, 15);
      for (let i = 0; i < 12; i++) { box(1.6, 15, 1.6, 0xeceae4, -38 + i * 6.9, -1, 27.5); box(1.6, 15, 1.6, 0xeceae4, -38 + i * 6.9, -1, -27.5); }
      box(26, 2, 14, 0x9aa3a8, 0, -1, 40);
      break;
    }
    case 'monument': {
      box(90, .4, 90, 0xc9c3b6, 0, -.2);
      box(14, 2, 14, 0xb7b0a2, 0, 0); box(10, 2, 10, 0xc6bfb0, 0, 2);
      cyl(1.4, 2.3, 26, 0xf2efe7, 0, 4, 0, 12);
      cyl(1.6, 1.6, 1.4, 0xd9a92e, 0, 30, 0, 12); cyl(.7, .9, 3.2, 0xd9a92e, 0, 31.4, 0, 8);
      const head = new THREE.Mesh(new THREE.SphereGeometry(.75, 10, 8), lam(0xd9a92e)); head.position.y = 35.2; G.add(head);
      [-1, 1].forEach(s => { const w = box(3.6, .4, 1.4, 0xd9a92e, s * 2.2, 33, 0); w.rotation.z = s * .5; });
      break;
    }
    case 'arena': {
      cyl(38, 38, 16, 0xd8d4c8, 0, -1, 0, 32); cyl(38.6, 38.6, 4, 0x3a4550, 0, 9, 0, 32);
      const d = new THREE.Mesh(new THREE.SphereGeometry(38, 32, 10, 0, Math.PI * 2, 0, Math.PI / 2), lam(0xbfc4c8)); d.scale.y = .22; d.position.y = 15; G.add(d);
      break;
    }
    case 'towers': {
      box(80, 10, 50, 0x8a99a6, 0, -1);
      [[-20, 0, 14, 128], [8, -8, 12, 104], [26, 10, 10, 82]].forEach(t => { const m = cyl(t[2], t[2], t[3], 0x5f86a8, t[0], 0, t[1], 24); m.scale.x = 1.5; cyl(t[2] * .9, t[2], 4, 0x9fb6c8, t[0], t[3], t[1], 24).scale.x = 1.5; });
      break;
    }
    case 'bazaar': {
      box(110, 10, 55, 0xd8c9a8, 0, -1);
      const r = new THREE.Mesh(new THREE.CylinderGeometry(27.5, 27.5, 110, 20, 1, false, 0, Math.PI), lam(0x3f8a5a)); r.rotation.z = Math.PI / 2; r.rotation.y = Math.PI / 2; r.scale.set(1, 1, .45); r.position.y = 9; G.add(r);
      break;
    }
    case 'dam': { // земляная плотина поперёк ущелья
      const g = new THREE.BoxGeometry(1, 1, 1), p = g.attributes.position;
      for (let i = 0; i < p.count; i++) { const top = p.getY(i) > 0; p.setXYZ(i, p.getX(i) * (top ? 720 : 140), top ? 150 : -20, p.getZ(i) * (top ? 36 : 380)); }
      g.computeVertexNormals(); const m = new THREE.Mesh(g, lam(0x9a9566)); G.add(m);
      box(1440, 4, 40, 0xb9b6ae, 0, 148);
      const stairs = new THREE.Mesh(new THREE.BoxGeometry(22, 2, 250), lam(0xe6e3dc)); stairs.position.set(0, 66, -104); stairs.rotation.x = -Math.atan2(170, 172); G.add(stairs);
      [-1, 1].forEach(k => { const t = new THREE.Mesh(new THREE.BoxGeometry(6, 1.5, 250), lam(0x5f6b3c)); t.position.set(k * 80, 66, -104); t.rotation.x = stairs.rotation.x; G.add(t); });
      const o = sampleAt(T, T.L, {}); G.rotation.y = Math.atan2(q.x - o.x, q.z - o.z);
      break;
    }
  }
  grp.add(G);
}
function nearLandmarks(T) {
  const out = [];
  LANDMARKS.forEach(lm => {
    const q = proj(lm.lat, lm.lon); let best = 1e18, bi = 0;
    for (let i = 0; i < T.N; i += 2) { const dx = T.X[i] - q.x, dz = T.Z[i] - q.z, d = dx * dx + dz * dz; if (d < best) { best = d; bi = i; } }
    const dist = Math.sqrt(best); if (dist > (lm.far ? 14000 : 1300)) return;
    const o = sampleAt(T, T.D[bi], {}), side = ((q.x - o.x) * o.rx + (q.z - o.z) * o.rz) > 0 ? 'right' : 'left';
    out.push(Object.assign({}, lm, { x: q.x, z: q.z, s: T.D[bi], side, dist }));
  });
  return out;
}
function addArch(grp, T, s, text, W) {
  const o = sampleAt(T, s, {}), g = new THREE.Group(), red = new THREE.MeshLambertMaterial({ color: 0xC3323B });
  [-1, 1].forEach(k => { const p = new THREE.Mesh(new THREE.BoxGeometry(.8, 6.5, .8), red); p.position.set(k * (W / 2 + 1), 3.25, 0); g.add(p); });
  const tex = canvasTex(1024, 128, (c, w, h) => { c.fillStyle = '#C3323B'; c.fillRect(0, 0, w, h); c.fillStyle = '#fff'; c.font = '700 76px Unbounded, sans-serif'; c.textAlign = 'center'; c.textBaseline = 'middle'; c.fillText(text, w / 2, h / 2 + 4); });
  const ban = new THREE.Mesh(new THREE.BoxGeometry(W + 3, 1.6, .5), [red, red, red, red, new THREE.MeshBasicMaterial({ map: tex }), new THREE.MeshBasicMaterial({ map: tex })]);
  ban.position.y = 6.2; g.add(ban);
  g.position.set(o.x, o.y, o.z); g.rotation.y = Math.atan2(o.tx, o.tz); grp.add(g);
}
