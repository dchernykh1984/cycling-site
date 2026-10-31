'use strict';
/* ---------------- Фоторежим ---------------- */
function stampText() { const d = new Date(), p = n => String(n).padStart(2, '0'); return { a: d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds()), b: 'ALATAU CAM ' + (world ? world.route.name.toUpperCase() : '') }; }
function updateStamp() { const s = stampText(); $('#stamp').innerHTML = '<span class="rec">● REC</span> ' + s.a + '<br>' + s.b; }
function syncPhotoUI() {
  const set = (id, out, v, f) => { $(id).value = v; $(out).textContent = f(v); };
  set('#pFov', '#oFov', look.fov, v => Math.round(v) + '°'); set('#pDist', '#oDist', look.dist, v => Math.round(v * 100)); set('#pCA', '#oCA', look.ca, v => Math.round(v * 1000));
  set('#pGrain', '#oGrain', look.grain, v => Math.round(v * 100)); set('#pVig', '#oVig', look.vig, v => Math.round(v * 100)); set('#pExp', '#oExp', look.exp, v => numF(+v, 2));
  document.querySelectorAll('#lookSeg button').forEach(b => b.setAttribute('aria-pressed', b.dataset.look === look.name ? 'true' : 'false'));
}
function enterPhoto() {
  if (phase === 'menu' || phase === 'countdown' || groupRide) return; photo = true; cam.yaw = 0; cam.pitch = 0; lookBeforePhoto = look.name; setPhotoCam(viewMode === 'chase' ? 'orbit' : 'fpv');
  $('#photoUI').classList.remove('hidden'); $('#hud').classList.toggle('hidden', !$('#pHud').checked); $('#stamp').classList.toggle('hidden', !$('#pStamp').checked); syncPhotoUI();
}
let lookBeforePhoto = 'bodycam';
function exitPhoto() { photo = false; cam.yaw = 0; cam.pitch = 0; cam.cinit = false; $('#photoUI').classList.add('hidden'); $('#stamp').classList.add('hidden'); $('#hud').classList.remove('hidden'); applyLook(lookBeforePhoto); }
function snap() {
  const glc = renderer.domElement, c = document.createElement('canvas'); c.width = glc.width; c.height = glc.height;
  const g = c.getContext('2d'); g.drawImage(glc, 0, 0);
  if ($('#pStamp').checked) { const s = stampText(), k = c.height / 900; g.font = '600 ' + Math.round(30 * k) + 'px Golos Text, monospace'; g.shadowColor = '#000'; g.shadowBlur = 4 * k; g.fillStyle = '#ff3b3b'; g.fillText('● REC', 34 * k, c.height - 74 * k); g.fillStyle = '#f4f4f0'; g.fillText(s.a, 160 * k, c.height - 74 * k); g.fillText(s.b, 34 * k, c.height - 34 * k); }
  $('#shotImg').src = c.toDataURL('image/jpeg', .92); $('#shot').classList.remove('hidden');
}
// жесты
let drag = null, pinch = null;
const glEl = document.getElementById('gl');
glEl.addEventListener('pointerdown', e => { if (!photo) return; drag = { x: e.clientX, y: e.clientY, id: e.pointerId }; glEl.setPointerCapture(e.pointerId); });
glEl.addEventListener('pointermove', e => {
  if (!photo || !drag || drag.id !== e.pointerId) return; const dx = (e.clientX - drag.x) / innerWidth, dy = (e.clientY - drag.y) / innerHeight; drag.x = e.clientX; drag.y = e.clientY;
  if (cam.mode === 'orbit') { cam.oyaw -= dx * 4; cam.opitch = clamp(cam.opitch + dy * 3, -.1, 1.4); } else { cam.yaw = clamp(cam.yaw - dx * 2.4, -1.6, 1.6); cam.pitch = clamp(cam.pitch - dy * 1.6, -.8, .8); }
});
glEl.addEventListener('pointerup', () => { drag = null; });
glEl.addEventListener('wheel', e => { if (photo && cam.mode === 'orbit') { cam.dist = clamp(cam.dist * (1 + e.deltaY * .001), 2.5, 40); e.preventDefault(); } }, { passive: false });
glEl.addEventListener('touchstart', e => { if (photo && e.touches.length === 2) { drag = null; pinch = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY); } }, { passive: true });
glEl.addEventListener('touchmove', e => { if (photo && pinch && e.touches.length === 2) { const d = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY); if (cam.mode === 'orbit') cam.dist = clamp(cam.dist * pinch / d, 2.5, 40); else { look.fov = clamp(look.fov * pinch / d, 40, 120); camera.fov = look.fov; camera.updateProjectionMatrix(); syncPhotoUI(); } pinch = d; } }, { passive: true });
glEl.addEventListener('touchend', () => { pinch = null; });
