'use strict';
/* ---------------- Главный цикл ---------------- */
let last = performance.now(), clockT = 0;
function frame(now) {
  requestAnimationFrame(frame);
  const dt = Math.min(.1, (now - last) / 1000); last = now; clockT += dt;
  Sensors.tick(now);
  if (phase === 'menu') { renderPreview(dt); return; } // на странице настроек 3D-сцену не рисуем
  if (!world) return;
  const T = world.T;
  let inp = { P: 0, cad: 0, mode: 'demo' }, grade = gradeAt(T, me.s);
  const frozen = paused || photo;
  if (phase === 'menu') {
    inp = { P: 0, cad: 80, mode: 'demo' }; me.s += me.v * dt; if (!T.loop && me.s > T.L - 200) { me.s = world.S0 + 10; cam.init = false; }
    bots.forEach(b => { b.s += b.v * dt; b.phase += 1.45 * Math.PI * 2 * dt; if (!T.loop && b.s > T.L - 150) b.s = world.S0 + 20; });
  } else if (!frozen) {
    inp = readInput();
    if (phase === 'countdown') {
      cdT -= dt; const n = Math.ceil(cdT); $('#count').textContent = n > 0 ? n : t('count.go');
      if (cdT <= 0) { phase = 'race'; updateModeUI(); }
      if (cdT < -0.8) $('#count').classList.add('hidden');
    } else if (phase === 'race' || phase === 'done') {
      if (cdT > -0.8) { cdT -= dt; if (cdT < -0.8) $('#count').classList.add('hidden'); }
      const y0 = sampleAt(T, me.s, _p1).y;
      if (phase === 'race') {
        raceT += dt; const ds = inp.direct ? directStep(me, inp.wheelKmh, dt) : stepRider(me, inp.P, grade, dt); me.s += ds; me.stats.dist += ds;
        const st = me.stats, y1 = sampleAt(T, me.s, _p1).y; if (y1 > y0) st.gain += y1 - y0;
        st.t += dt; st.sumP += inp.P * dt; if (inp.cad > 0) { st.sumCad += inp.cad; st.nCad++; } st.maxV = Math.max(st.maxV, me.v); if (inp.mode === 'demo') st.demoT += dt; me.pAcc += inp.P * dt; me.pT += dt; if (me.pT >= 1) { me.powerLog.push(me.pAcc / me.pT); me.pAcc = 0; me.pT = 0; if (me.track.length < MAX_TRACK) me.track.push(trackPoint(inp)); } if (inp.mode === 'power') st.real = true; const hrNow = Sensors.hr(); if (hrNow) { st.sumHR += hrNow; st.nHR++; st.maxHR = Math.max(st.maxHR, hrNow); }
        if (rideMode === 'plan' || rideMode === 'free') {
          // тренировка по плану: маршрут крутится кругами, финиш — когда закончится последний шаг
          if (!T.loop && me.s >= T.L - 15) { me.s = world.S0; cam.cinit = false; cam.init = false; }
          const lap = Math.floor(me.stats.dist / (world.FIN - world.S0));
          if (lap > me.lap) { me.lap = lap; world.lms.forEach(l => { l.done = false; }); toast(t('hud.lapToast', { n: lap + 1 }), 2.5); }
          if (rideMode === 'plan' && Work.update(dt, inp.cad, inp.mode)) finishWorkout();
        } else if (me.s >= world.FIN) { me.finishT = raceT; finishRace(); }
        world.lms.forEach(l => { if (l.done || l.dist > 700) return; let ahead = l.s - me.s; if (T.loop) ahead = ((ahead % T.L) + T.L) % T.L; if (ahead < 220 && ahead > -40) { l.done = true; toast(l.side === 'right' ? t('sight.right', { name: l.name }) : t('sight.left', { name: l.name }), 4.5); } });
      } else { me.s += stepRider(me, 60, grade, dt); }
    }
    bots.forEach(b => {
      if (b.remote) { mpStepRemote(b, dt); return; }
      if (phase === 'countdown') return;
      const gb = gradeAt(T, b.s), surge = 1 + .08 * Math.sin(clockT * .21 + b.seed) + .05 * Math.sin(clockT * .9 + b.seed * 2) + (gb > .03 ? .08 : 0);
      const P = b.finishT != null ? 70 : b.wkg * b.mass * surge * styleMult(b, gb);
      b.P = P;
      b.cad = b.v > .5 ? clamp((b.finishT != null ? 62 : (b.ch.style === 'sprinter' ? 94 : b.ch.style === 'climber' ? 86 : 90)) + Math.sin(clockT * .37 + b.seed) * 4 - Math.max(0, gb) * 120, 58, 115) : 0;
      b.s += stepRider(b, P, gb, dt); b.phase += b.cad / 60 * Math.PI * 2 * dt;
      if (b.finishT == null && phase !== 'menu' && b.s >= world.FIN) b.finishT = raceT;
      if (!T.loop && b.s > T.L - 2) b.s = T.L - 2;
    });
    if (!T.loop && me.s > T.L - 1) me.s = T.L - 1;
  }
  // боты: позиция и анимация
  bots.forEach(b => { const o = riderPos(b, _p0); b.mesh.g.position.set(o.px, o.y, o.pz); b.mesh.g.rotation.y = Math.atan2(o.tx, o.tz); b.mesh.g.rotation.x = -Math.atan(gradeAt(T, b.s)); poseRider(b.mesh, b.phase); });
  updateCamera(frozen ? 0 : dt, frozen ? 0 : inp.cad || 0, me.v);
  Trainer.update(clockT, phase === 'race' && !frozen ? grade * 100 : 0);
  MP.lastInp = inp;
  // пост-обработка
  const u = postMat.uniforms;
  u.uTime.value = clockT; u.uDist.value = look.dist; u.uCA.value = look.ca; u.uGrain.value = look.grain; u.uVig.value = look.vig; u.uExp.value = look.exp; u.uSat.value = look.sat; u.uCon.value = look.con; u.uMono.value = look.mono; u.uTint.value.set(look.tint[0], look.tint[1], look.tint[2]);
  u.uBlur.value = photo ? 0 : look.blur * clamp((me.v - 5) / 14, 0, 1) * .045;
  renderer.setRenderTarget(rt); renderer.render(scene, camera);
  u.tD.value = rt.texture; renderer.setRenderTarget(null); renderer.render(postScene, postCam);
  // интерфейс
  if (phase === 'menu') renderPreview(dt);
  if (phase !== 'menu') { hudAcc += dt; if (hudAcc > .1) { hudAcc = 0; updateHUD(inp, grade); } }
  placeTags();
  if (toastT > 0) { toastT -= dt; if (toastT <= 0) $('#toast').classList.remove('show'); }
  if (photo && $('#pStamp').checked) updateStamp();
}
