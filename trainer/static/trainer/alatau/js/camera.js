'use strict';
/* ---------------- Камера ---------------- */
const cam = { q: new THREE.Quaternion(), init: false, yaw: 0, pitch: 0, dist: 7, oyaw: .6, opitch: .25 };
const _p0 = {}, _p1 = {}, _m4 = new THREE.Matrix4(), _v1 = new THREE.Vector3(), _v2 = new THREE.Vector3(), _qd = new THREE.Quaternion(), _e = new THREE.Euler(0, 0, 0, 'YXZ');
function riderPos(R, out) { const o = sampleAt(world.T, R.s, out); o.px = o.x + o.rx * R.lane; o.pz = o.z + o.rz * R.lane; return o; }
let viewMode = 'fpv';
const _p2 = {}, _v3 = new THREE.Vector3();
function setFov(f) { if (Math.abs(camera.fov - f) > .01) { camera.fov = f; camera.updateProjectionMatrix(); } }
function updateCamera(dt, cad, speed) {
  const T = world.T, o = riderPos(me, _p0), a = sampleAt(T, me.s + 9, _p1);
  me.phase += (cad / 60) * Math.PI * 2 * dt;
  const sw = look.sway, ph = me.phase, rough = Math.min(1, speed / 12);
  if (photo && cam.mode === 'orbit') {
    const c = _v1.set(o.px, o.y + 1, o.pz);
    camera.position.set(c.x + Math.sin(cam.oyaw) * Math.cos(cam.opitch) * cam.dist, c.y + Math.sin(cam.opitch) * cam.dist, c.z + Math.cos(cam.oyaw) * Math.cos(cam.opitch) * cam.dist);
    camera.lookAt(c); playerAvatar.g.visible = true; bars.visible = false; setFov(look.fov);
  } else if (!photo && viewMode === 'chase') {
    // вид от третьего лица: камера едет за гонщиком по той же полосе
    playerAvatar.g.visible = true; bars.visible = false; setFov(Math.min(look.fov, 78));
    const b = sampleAt(T, me.s - 6.5, _p2), f = sampleAt(T, me.s + 7, _p1);
    _v3.set(b.x + b.rx * me.lane, Math.max(b.y, o.y) + 2.3 + (Math.random() - .5) * .01 * rough * sw, b.z + b.rz * me.lane);
    if (!cam.cinit) { camera.position.copy(_v3); cam.cinit = true; } else camera.position.lerp(_v3, 1 - Math.exp(-dt * 6));
    _v2.set(f.x + f.rx * me.lane, f.y + 1.05, f.z + f.rz * me.lane);
    camera.lookAt(_v2);
  } else {
    const bob = (Math.sin(ph * 2) * .012 + (Math.random() - .5) * .006 * rough) * sw;
    const lat = Math.sin(ph) * .025 * sw * (cad > 0 ? 1 : 0);
    playerAvatar.g.visible = false; bars.visible = true; setFov(look.fov);
    camera.position.set(o.px + o.rx * lat, o.y + look.h + bob, o.pz + o.rz * lat);
    _v2.set(a.x + a.rx * me.lane, a.y + look.h - .25, a.z + a.rz * me.lane);
    _m4.lookAt(camera.position, _v2, camera.up); _qd.setFromRotationMatrix(_m4);
    if (!cam.init) { cam.q.copy(_qd); cam.init = true; } else cam.q.slerp(_qd, 1 - Math.exp(-dt * 5));
    camera.quaternion.copy(cam.q);
    _e.set(cam.pitch + Math.sin(ph * 2 + 1) * .006 * sw, cam.yaw, Math.sin(ph) * .018 * sw * (cad > 0 ? 1 : 0));
    _qd.setFromEuler(_e); camera.quaternion.multiply(_qd);
    bars.rotation.z = -Math.sin(ph) * .02 * sw;
  }
  playerAvatar.g.position.set(o.px, o.y, o.pz); playerAvatar.g.rotation.y = Math.atan2(o.tx, o.tz); playerAvatar.g.rotation.x = -Math.atan(gradeAt(T, me.s));
  poseRider(playerAvatar, me.phase);
  sky.position.copy(camera.position);
}
function setView(v, quiet) {
  viewMode = v; cam.cinit = false; cam.init = false;
  $('#btnView').setAttribute('aria-label', v === 'chase' ? t('view.toFirst') : t('view.toThird'));
  if (!quiet) toast(v === 'chase' ? t('view.toThird') : t('view.toFirst'));
}
function setPhotoCam(mode) {
  cam.mode = mode;
  if (mode === 'orbit') { const o = sampleAt(world.T, me.s, {}); cam.oyaw = Math.atan2(-o.tx, -o.tz) + .55; cam.opitch = .22; cam.dist = 6; }
  document.querySelectorAll('#camSeg button').forEach(x => x.setAttribute('aria-pressed', x.dataset.cam === mode ? 'true' : 'false'));
}
function applyLook(name) {
  const L = LOOKS[name] || LOOKS.bodycam; Object.assign(look, L); look.name = name;
  camera.fov = look.fov; camera.updateProjectionMatrix(); syncPhotoUI();
}
