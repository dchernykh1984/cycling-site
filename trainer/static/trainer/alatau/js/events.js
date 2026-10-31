'use strict';
/* ---------------- События ---------------- */
$('#btnConnect').onclick = () => Sensors.add();
$('#btnStart').onclick = async () => { groupRide = null; if (mpMyGroup()) await mpLeaveMyGroup(); startRace(); };
$('#mpCreate').onclick = mpCreateGroup;
// когда шрифт загрузится, перерисовываем форму, чтобы надпись была нужным шрифтом
try { document.fonts && document.fonts.ready.then(() => { if (!renderer) return; setPlayerChar(settings.char); setPreview(settings.char); }); } catch (e) {} // no 3D on this device: the page already said so
$('#btnRecords').onclick = () => { renderRecords(); $('#recM').classList.remove('hidden'); };
$('#btnRecClose').onclick = () => $('#recM').classList.add('hidden');
$('#btnRecReset').onclick = e => { const b = e.currentTarget; if (!b.dataset.armed) { b.dataset.armed = '1'; b.textContent = t('records.resetSure'); return; } Records.reset(); renderRecords(); renderMenu(); };
['#circ', '#trainer', '#cadSpeed', '#bikeType', '#bikeKg', '#height', '#mass', '#bots', '#level', '#difficulty', '#hrmax', '#view'].forEach(id => $(id).addEventListener('change', () => { readSettings(); renderStartSum(); if (id === '#bikeType') { const bt = bikeType(); settings.bikeKg = bt.kg; settings.circ = bt.circ; $('#bikeKg').value = bt.kg; $('#circ').value = bt.circ; store.set('settings', settings); }
    if (id === '#bikeKg') $('#bikeKg').value = settings.bikeKg;
    if (id === '#height' || id === '#mass' || id === '#bikeType' || id === '#bikeKg') { if (id === '#height' || id === '#mass') $(id).value = id === '#height' ? settings.height : settings.mass; renderBodyHint(); setPlayerChar(settings.char); setPreview(settings.char); renderStartSum(); } if (id === '#view' && phase === 'menu') setView(settings.view, true); updateModeUI(); }));
$('#demoP').addEventListener('input', e => { demoP = +e.target.value; $('#demoV').textContent = demoP + ' ' + t('u.w'); });
$('#gUp').onclick = () => { gearR = Math.min(bikeR().length, gearR + 1); updateModeUI(); };
$('#gDown').onclick = () => { gearR = Math.max(1, gearR - 1); updateModeUI(); };
$('#gearV').parentElement.style.pointerEvents = 'auto'; $('#gearV').title = t('plan.chainringTitle');
$('#gearV').onclick = () => { gearF = gearF >= bikeF().length ? 1 : gearF + 1; updateModeUI(); };
document.querySelectorAll('#modeSeg button').forEach(b => b.onclick = () => { settings.mode = b.dataset.mode; store.set('settings', settings); renderPlanEditor(); });
$('#plFront').onchange = e => { settings.plan.front = e.target.value; savePlan(); renderPlanEditor(); updateModeUI(); };
$('#plCass').onchange = e => { settings.plan.cass = e.target.value; savePlan(); renderPlanEditor(); updateModeUI(); };
$('#plFrontCustom').onchange = e => { const a = parseTeeth(e.target.value, 20, 60).sort((x, y) => x - y).slice(0, 3); if (a.length) { settings.plan.frontCustom = a; savePlan(); } renderPlanEditor(); updateModeUI(); };
$('#plCassCustom').onchange = e => { const a = parseTeeth(e.target.value, 9, 52).sort((x, y) => y - x).slice(0, 13); if (a.length >= 2) { settings.plan.cassCustom = a; savePlan(); } else btHint(t('bt.twoSprockets'), true); renderPlanEditor(); updateModeUI(); };
$('#plStartF').onchange = e => shiftPlan(+e.target.value - settings.plan.steps[0].f, 0);
$('#plStartR').onchange = e => shiftPlan(0, +e.target.value - settings.plan.steps[0].r);
$('#plAdd').onclick = () => { const st = settings.plan.steps, l = st[st.length - 1]; st.push({ f: l.f, r: Math.min(bikeR().length, l.r + 1), cad: l.cad, min: l.min }); savePlan(); renderPlanEditor(); };
$('#plTpl').onclick = () => { const d = defaultPlan(); settings.plan.steps = d.steps; savePlan(); renderPlanEditor(); };
$('#btnPause').onclick = () => { if (phase === 'race' || phase === 'countdown') { paused = !groupRide; $('#pauseM').classList.remove('hidden'); } };
$('#btnResume').onclick = () => { paused = false; $('#pauseM').classList.add('hidden'); };
$('#btnFinish').onclick = () => { $('#pauseM').classList.add('hidden'); paused = false; if (rideMode === 'free') finishFree(); else if (rideMode === 'plan' && phase === 'race') finishWorkout(); };
$('#btnQuit').onclick = () => { $('#pauseM').classList.add('hidden'); $('#count').classList.add('hidden'); startMenu(); };
$('#btnAgain').onclick = () => { $('#resM').classList.add('hidden'); groupRide = null; startRace(); }; // a group race is ridden once: again is alone
$('#btnMenu').onclick = () => { startMenu(); renderMenu(); };
$('#btnPhoto').onclick = enterPhoto;
$('#btnPhotoExit').onclick = exitPhoto;
$('#btnSnap').onclick = snap;
$('#btnShotClose').onclick = () => $('#shot').classList.add('hidden');
document.querySelectorAll('#camSeg button').forEach(b => b.onclick = () => setPhotoCam(b.dataset.cam));
$('#btnView').onclick = () => setView(viewMode === 'chase' ? 'fpv' : 'chase');
document.querySelectorAll('#lookSeg button').forEach(b => b.onclick = () => applyLook(b.dataset.look));
const bindSl = (id, key, isFov) => $(id).addEventListener('input', e => { look[key] = +e.target.value; if (isFov) { camera.fov = look.fov; camera.updateProjectionMatrix(); } look.name = 'custom'; syncPhotoUI(); });
bindSl('#pFov', 'fov', true); bindSl('#pDist', 'dist'); bindSl('#pCA', 'ca'); bindSl('#pGrain', 'grain'); bindSl('#pVig', 'vig'); bindSl('#pExp', 'exp');
$('#pStamp').addEventListener('change', e => $('#stamp').classList.toggle('hidden', !e.target.checked));
$('#pHud').addEventListener('change', e => $('#hud').classList.toggle('hidden', !e.target.checked));
window.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
  if (e.key === 'ArrowUp' || e.key === 'w') { demoP = clamp(demoP + 10, 0, 450); $('#demoP').value = demoP; $('#demoV').textContent = demoP + ' ' + t('u.w'); }
  if (e.key === 'ArrowDown' || e.key === 's') { demoP = clamp(demoP - 10, 0, 450); $('#demoP').value = demoP; $('#demoV').textContent = demoP + ' ' + t('u.w'); }
  if (e.key === ']') $('#gUp').click(); if (e.key === '[') $('#gDown').click();
  if ((e.key === 'v' || e.key === 'м') && !photo) $('#btnView').click();
  if (e.key === 'p' || e.key === 'з') photo ? exitPhoto() : enterPhoto();
  if (e.key === ' ' && (phase === 'race' || phase === 'countdown')) { e.preventDefault(); paused ? $('#btnResume').click() : $('#btnPause').click(); }
});
document.addEventListener('visibilitychange', () => {
  if (document.hidden && phase === 'race' && !groupRide) { paused = true; $('#pauseM').classList.remove('hidden'); }
  if (!document.hidden) {
    // после возврата на страницу проверяем связь: браузер мог тихо разорвать её, пока экран был выключен
    Sensors.devs.forEach(d => { if (!d.manual && !d.reconnecting && !(d.dev.gatt && d.dev.gatt.connected)) d.onDisc(); });
    if (phase === 'race' || phase === 'countdown') { try { navigator.wakeLock && navigator.wakeLock.request('screen').catch(() => {}); } catch (e) {} }
  }
});
