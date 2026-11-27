'use strict';
/* ---------------- Главный цикл ---------------- */
// Each frame the ride takes its step (js/ride.js) and the trainer is told the grade; then the scene and
// the HUD are drawn from the ride's state. The drawing writes nothing the ride reads: only the turn of
// the pedals (a rider's phase), which nothing but the drawing uses.
let last = performance.now(), clockT = 0;
Object.assign(rideHooks, {
  go: () => updateModeUI(),
  backToStart: () => { cam.cinit = false; cam.init = false; },
  lap: n => toast(t('hud.lapToast', { n }), 2.5),
  sight: l => toast(t(l.said === 'mountains' ? 'sight.mountains' : l.side === 'right' ? 'sight.right' : 'sight.left', { name: l.name }), 4.5),
  finish: () => finishRace(),
  routeEnd: () => finishFree(),
  crossing: (point, last, ago) => mpCrossing(point, last, ago),
  planStep: (i, s, shifted) => { if (shifted) updateModeUI(); toast(s.f != null ? t('plan.stepToast', { n: i + 1, g: gearLabel(s.f, s.r), c: s.cad }) : t('plan.stepToastW', { n: i + 1, what: stepWhat(s) }), 5); },
  planSoon: s => toast(s.f != null ? t('plan.soon', { g: gearLabel(s.f, s.r), c: s.cad }) : t('plan.soonW', { what: stepWhat(s) }), 4),
  planCue: text => toast(text, 6),
  planDone: () => planOver()
});
function frame(now) {
  requestAnimationFrame(frame);
  const dt = Math.min(MAX_FRAME, (now - last) / 1000); last = now; clockT += dt;
  Sensors.tick(now);
  // на странице настроек 3D-сцену не рисуем; a smart trainer is let go back to a flat road, not left holding a workout's power
  if (phase === 'menu') { Trainer.update(clockT, 0, me, null); renderPreview(dt); return; }
  if (!world) return;
  const T = world.T, frozen = paused || photo, grade = gradeAt(T, me.s);
  const inp = frozen ? { P: 0, cad: 0, mode: 'demo' } : readInput();
  if (!frozen) { advanceRide(dt, inp, clockT); showCount(); }
  // the grade, or the power of a workout's step while ERG is on (Trainer holds it on a trainer that can)
  const riding = phase === 'race' && !frozen;
  Trainer.update(clockT, riding ? grade * 100 : 0, me, riding && rideMode === 'plan' && settings.erg !== false ? Work.target() : null);
  MP.lastInp = inp;
  // боты: позиция и анимация
  bots.forEach(b => {
    if (!frozen) b.phase += (b.cad || 0) / 60 * Math.PI * 2 * dt;
    const o = riderPos(b, _p0), m = riderModels.get(b); m.g.position.set(o.px, o.y, o.pz); m.g.rotation.y = riderHeading(b); m.g.rotation.x = -Math.atan(gradeAt(T, b.s)); poseRider(m, b.phase);
  });
  updateCamera(frozen ? 0 : dt, frozen ? 0 : inp.cad || 0, me.v);
  // пост-обработка
  const u = postMat.uniforms;
  u.uTime.value = clockT; u.uDist.value = look.dist; u.uCA.value = look.ca; u.uGrain.value = look.grain; u.uVig.value = look.vig; u.uExp.value = look.exp; u.uSat.value = look.sat; u.uCon.value = look.con; u.uMono.value = look.mono; u.uTint.value.set(look.tint[0], look.tint[1], look.tint[2]);
  u.uBlur.value = photo ? 0 : look.blur * clamp((me.v - 5) / 14, 0, 1) * .045;
  renderer.setRenderTarget(rt); renderer.render(scene, camera);
  u.tD.value = rt.texture; renderer.setRenderTarget(null); renderer.render(postScene, postCam);
  // интерфейс
  hudAcc += dt; if (hudAcc > .1) { hudAcc = 0; updateHUD(inp, grade); }
  placeTags();
  if (toastT > 0) { toastT -= dt; if (toastT <= 0) $('#toast').classList.remove('show'); }
  if (photo && $('#pStamp').checked) updateStamp();
}
