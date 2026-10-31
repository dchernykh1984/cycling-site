'use strict';
/* ---------------- Настоящие здания и улицы из OpenStreetMap (файл alatau_osm.json) ---------------- */
// Хранилище в браузере (IndexedDB): файл бывает в несколько мегабайт, localStorage столько не вмещает
const IDB = {
  db: null,
  open() { return new Promise((res, rej) => { try { const r = indexedDB.open('alatau', 1); r.onupgradeneeded = () => r.result.createObjectStore('kv'); r.onsuccess = () => res(this.db = r.result); r.onerror = () => rej(r.error); } catch (e) { rej(e); } }); },
  async op(mode, fn) { const db = this.db || await this.open(); return new Promise((res, rej) => { const st = db.transaction('kv', mode).objectStore('kv'), rq = fn(st); rq.onsuccess = () => res(rq.result); rq.onerror = () => rej(rq.error); }); },
  get(k) { return this.op('readonly', s => s.get(k)); }, set(k, v) { return this.op('readwrite', s => s.put(v, k)); }, del(k) { return this.op('readwrite', s => s.delete(k)); }
};
let OSM = null;
function validOSM(d) { return d && d.v === 1 && d.routes && typeof d.routes === 'object'; }
function applyOSM(d) {
  OSM = validOSM(d) ? d : null;
  ROUTES.forEach(r => { const x = OSM && OSM.routes[r.id]; r.osm = x && Array.isArray(x.path) && x.path.length > 3 ? x : null; });
  renderOSMStatus();
}
function osmCount() { return OSM ? Object.values(OSM.routes).reduce((a, r) => a + ((r.buildings && r.buildings.length) || 0), 0) : 0; }
function renderOSMStatus() {
  const el = $('#osmStatus'); if (!el) return;
  if (OSM) {
    const ids = ROUTES.filter(r => r.osm).map(r => r.name);
    el.textContent = 'Загружено ' + osmCount().toLocaleString('ru-RU') + ' зданий из OpenStreetMap. Улицы выровнены на маршрутах: ' + ids.join(', ') + '.';
    $('#osmClear').classList.remove('hidden');
  } else {
    el.textContent = 'Сейчас дома вдоль маршрутов сгенерированы. Загрузите файл alatau_osm.json из скрипта выгрузки, и появятся настоящие здания Алматы и точная геометрия улиц.';
    $('#osmClear').classList.add('hidden');
  }
}
async function loadOSM() {
  try { const t = await Promise.race([IDB.get('osm'), new Promise(r => setTimeout(() => r(null), 2500))]); if (t) applyOSM(JSON.parse(t)); else renderOSMStatus(); }
  catch (e) { renderOSMStatus(); }
}
async function importOSMFile(file) {
  const el = $('#osmStatus');
  try {
    el.textContent = 'Читаю файл…'; const text = await file.text(); const d = JSON.parse(text);
    if (!validOSM(d)) { el.textContent = 'Это не тот файл: нужен alatau_osm.json, который создаёт скрипт выгрузки.'; return; }
    try { await IDB.set('osm', text); } catch (e) {}
    applyOSM(d); rebuildMenuWorld();
  } catch (e) { el.textContent = 'Не удалось прочитать файл: ' + e.message; }
}
function rebuildMenuWorld() { showLoading(true); setTimeout(() => { world = null; renderMenu(); startMenu(); cam.init = false; cam.cinit = false; showLoading(false); }, 30); }

// Подготовка зданий: метры, центр, радиус и сетка для быстрых проверок
function prepOSM(arr) {
  const list = [], g = new Map(), cell = 40;
  (arr || []).forEach(a => {
    if (!Array.isArray(a) || a.length < 8) return;
    const h = a[0] / 10, mh = a[1] / 10; if (mh > .5) return; // части зданий на высоте пропускаем
    const ring = []; for (let i = 2; i + 1 < a.length; i += 2) ring.push([a[i] / 10, a[i + 1] / 10]);
    if (ring.length < 3) return;
    let cx = 0, cz = 0; ring.forEach(p => { cx += p[0]; cz += p[1]; }); cx /= ring.length; cz /= ring.length;
    let r = 0; ring.forEach(p => { r = Math.max(r, Math.hypot(p[0] - cx, p[1] - cz)); });
    const b = { ring, h: clamp(h, 3, 320), cx, cz, r }; list.push(b);
    const k = Math.floor(cx / cell) + ',' + Math.floor(cz / cell); (g.get(k) || g.set(k, []).get(k)).push(b);
  });
  return {
    list,
    hit(x, z) { const ci = Math.floor(x / cell), cj = Math.floor(z / cell); for (let a = -2; a <= 2; a++) for (let d = -2; d <= 2; d++) { const L = g.get((ci + a) + ',' + (cj + d)); if (L) for (const b of L) if (Math.hypot(b.cx - x, b.cz - z) < b.r + 1.5) return true; } return false; }
  };
}
// Все здания маршрута — одна геометрия: стены, крыша, цвет фасада в вершинах
function addOSMBuildings(grp, T, W, lms, osmB) {
  const cell = 30, rg = new Map();
  for (let i = 0; i < T.N; i += 2) { const k = Math.floor(T.X[i] / cell) + ',' + Math.floor(T.Z[i] / cell); (rg.get(k) || rg.set(k, []).get(k)).push(i); }
  const roadD = (x, z) => { let b = 1e9; const ci = Math.floor(x / cell), cj = Math.floor(z / cell); for (let a = -1; a <= 1; a++) for (let d = -1; d <= 1; d++) { const L = rg.get((ci + a) + ',' + (cj + d)); if (L) for (const i of L) { const v = Math.hypot(T.X[i] - x, T.Z[i] - z); if (v < b) b = v; } } return b; };
  const pal = [0xd8cfbf, 0xc9c2b5, 0xe2dccd, 0xb9b5ad, 0xd6c4a8, 0xc7cdd1, 0xe8e3d8, 0xb7a993, 0xcfc1a9], glass = 0x7f97ab;
  const P = [], N = [], C = [], c = new THREE.Color(); let kept = 0;
  const push = (x, y, z, nx, ny, nz) => { P.push(x, y, z); N.push(nx, ny, nz); C.push(c.r, c.g, c.b); };
  osmB.list.forEach((b, bi) => {
    if (lms.some(l => Math.hypot(l.x - b.cx, l.z - b.cz) < l.r + b.r * .5)) return;   // на месте наших достопримечательностей
    if (b.ring.some(p => roadD(p[0], p[1]) < W / 2 + 5.5)) return;                    // ничего на проезжей части и тротуаре
    const base = terrainH(T, b.cx, b.cz) - 1.5, top = base + 1.5 + b.h;
    let area = 0; const R0 = b.ring; for (let i = 0; i < R0.length; i++) { const p = R0[i], q = R0[(i + 1) % R0.length]; area += p[0] * q[1] - q[0] * p[1]; }
    const R = area > 0 ? R0.slice().reverse() : R0; // обход, при котором нормали стен смотрят наружу
    c.setHex(b.h > 45 ? glass : pal[(bi * 2654435761 >>> 0) % pal.length]);
    for (let i = 0; i < R.length; i++) {
      const p = R[i], q = R[(i + 1) % R.length], ex = q[0] - p[0], ez = q[1] - p[1], L = Math.hypot(ex, ez) || 1, nx = -ez / L, nz = ex / L;
      push(p[0], base, p[1], nx, 0, nz); push(q[0], base, q[1], nx, 0, nz); push(q[0], top, q[1], nx, 0, nz);
      push(p[0], base, p[1], nx, 0, nz); push(q[0], top, q[1], nx, 0, nz); push(p[0], top, p[1], nx, 0, nz);
    }
    let tris = []; try { tris = THREE.ShapeUtils.triangulateShape(R.map(p => new THREE.Vector2(p[0], p[1])), []); } catch (e) {}
    tris.forEach(t => {
      let [a, b2, d] = t; const A = R[a], B = R[b2], D = R[d];
      if ((B[1] - A[1]) * (D[0] - A[0]) - (B[0] - A[0]) * (D[1] - A[1]) < 0) { const tmp = b2; b2 = d; d = tmp; }
      [a, b2, d].forEach(k => push(R[k][0], top, R[k][1], 0, 1, 0));
    });
    kept++;
  });
  if (!P.length) return 0;
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(P, 3)); g.setAttribute('normal', new THREE.Float32BufferAttribute(N, 3)); g.setAttribute('color', new THREE.Float32BufferAttribute(C, 3));
  g.computeBoundingSphere(); grp.add(new THREE.Mesh(g, osmMat));
  return kept;
}
