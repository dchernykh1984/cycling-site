'use strict';
/* ---------------- Запуск ---------------- */
(function boot() {
  if (!window.THREE) { $('#loading').textContent = t('boot.noThree'); return; }
  try {
    $('#demoV').textContent = demoP + ' ' + t('u.w');
    Records.load(); initGL(); makeMaterials(); fillSettings(); renderMenu(); initPreview(); renderChars(); setPreview(settings.char); renderPlanEditor();
    if (!Sensors.supported()) btHint(isIOS() ? t('bt.iosBoot') : t('bt.noneBoot'), true);
    applyOSM(null); try { IDB.del('osm').catch(() => {}); } catch (e) {} // загрузка карты города отключена
    startMenu(); showLoading(false); Records.connect().then(mpInit); requestAnimationFrame(t => { last = t; frame(t); });
  } catch (e) { console.error(e); $('#loading').textContent = t('boot.failed', { msg: e.message }); }
})();
