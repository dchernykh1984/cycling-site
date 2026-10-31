'use strict';
/* ---------------- Подписи над соперниками ---------------- */
let tagEls = [];
const _tv = new THREE.Vector3();
function ensureTags() {
  if (tagEls.length === bots.length && tagEls.every((t, i) => t.b === bots[i])) return;
  const box = $('#tags'); box.innerHTML = '';
  tagEls = bots.map(b => {
    const el = document.createElement('div'); el.className = 'tag3d'; el.style.borderLeftColor = hexs(b.color);
    el.innerHTML = '<div class="nm"></div><div class="r"><b class="g">0</b><span>' + t('u.s') + '</span></div><div class="r"><b class="c">0</b><span>' + t('u.rpm') + '</span></div><div class="r"><b class="p">0</b><span>' + t('u.w') + '</span></div>';
    el.querySelector('.nm').textContent = b.name; box.appendChild(el);
    return { b, el, nm: el.querySelector('.nm'), g: el.querySelector('.g'), c: el.querySelector('.c'), p: el.querySelector('.p') };
  });
}
function updateTagText() {
  ensureTags();
  tagEls.forEach(t => {
    const b = t.b, dist = b.s - me.s, sec = Math.round(Math.abs(dist) / Math.max((me.v + b.v) / 2, 3));
    t.g.textContent = sec === 0 ? '0' : (dist > 0 ? '+' : '−') + sec;
    t.g.className = 'g ' + (sec === 0 ? '' : dist > 0 ? 'ahead' : 'behind');
    if (t.nm.textContent !== b.name) t.nm.textContent = b.name;
    t.c.textContent = Math.round(b.cad || 0); t.p.textContent = Math.round(b.P || 0);
  });
}
// позиция подписи: проекция точки над головой с учётом искажения линзы (обратная бочка)
function placeTags() {
  const box = $('#tags');
  if (phase === 'menu' || !world) { box.style.display = 'none'; return; }
  box.style.display = ''; ensureTags();
  const W = innerWidth, H = innerHeight, a = W / H, k = look.dist, rm = .25 * (a * a + 1);
  camera.updateMatrixWorld();
  const vis = [];
  tagEls.forEach(t => {
    const g = t.b.mesh.g, sz = (t.b.ch && t.b.ch.size) || 1;
    _tv.set(g.position.x, g.position.y + 2.05 * sz, g.position.z);
    const d = _tv.distanceTo(camera.position); _tv.project(camera);
    if (_tv.z > 1 || d > 140 || d < 2.2) { t.el.style.display = 'none'; return; }
    let cx = _tv.x * .5 * a, cy = _tv.y * .5;
    if (k > .001) { const rs = Math.hypot(cx, cy); if (rs > 1e-5) { let r = rs; for (let i = 0; i < 6; i++) { const f = r * (1 + k * r * r) / (1 + k * rm) - rs, df = (1 + 3 * k * r * r) / (1 + k * rm); r -= f / df; } cx *= r / rs; cy *= r / rs; } }
    const x = (cx / a + .5) * W, y = (.5 - cy) * H;
    if (x < -80 || x > W + 80 || y < -40 || y > H + 120) { t.el.style.display = 'none'; return; }
    if (!t.w) { t.el.style.display = ''; t.w = t.el.offsetWidth || 90; t.h = t.el.offsetHeight || 64; }
    vis.push({ t, x, y, d, sc: clamp(1.15 - d / 110, .62, 1) });
  });
  // ближние подписи на месте, дальние сдвигаем вверх, чтобы не перекрывались
  vis.sort((p, q) => p.d - q.d);
  const placed = [];
  vis.forEach(v => {
    const w = v.t.w * v.sc + 4, h = v.t.h * v.sc + 3; let bottom = v.y, ok = false;
    for (let n = 0; n < 4 && !ok; n++) {
      const hit = placed.find(r => Math.abs(r.x - v.x) < (r.w + w) / 2 && bottom > r.top && bottom - h < r.bottom);
      if (!hit) ok = true; else bottom = hit.top - 2;
    }
    if (!ok || bottom - h < 70) { v.t.el.style.display = 'none'; return; }
    placed.push({ x: v.x, w, top: bottom - h, bottom });
    const el = v.t.el;
    el.style.display = ''; el.style.opacity = clamp((140 - v.d) / 40, 0, 1).toFixed(2); el.style.zIndex = String(1000 - Math.round(v.d));
    el.style.transform = 'translate(' + v.x.toFixed(1) + 'px,' + bottom.toFixed(1) + 'px) scale(' + v.sc.toFixed(2) + ') translate(-50%,-100%)';
  });
}
