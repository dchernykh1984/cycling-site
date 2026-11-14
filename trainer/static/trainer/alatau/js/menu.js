'use strict';
/* ---------------- Меню ---------------- */
function sparkline(cv, route) {
  const T = buildTrack(route), dpr = 2, g = cv.getContext('2d'); cv.width = 96 * dpr; cv.height = 38 * dpr;
  const o = {}, ys = []; let mn = 1e9, mx = -1e9; for (let i = 0; i <= 60; i++) { const y = sampleAt(T, T.L * i / 60, o).y; ys.push(y); mn = Math.min(mn, y); mx = Math.max(mx, y); }
  const r = Math.max(40, mx - mn); g.beginPath(); g.moveTo(0, cv.height);
  ys.forEach((y, i) => g.lineTo(i / 60 * cv.width, cv.height - 3 - (y - mn) / r * (cv.height - 8))); g.lineTo(cv.width, cv.height); g.closePath();
  g.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--apple').trim() || '#C3323B'; g.globalAlpha = .85; g.fill();
  return T;
}
function pickRoute(id) { routeSel = id; store.set('route', id); renderMenu(); if (MP.status === 'on') mpSchedule(200); }
function renderMenu() {
  const city = (ROUTES.find(r => r.id === routeSel) || ROUTES[0]).city; // the map of the chosen route: its routes are listed
  $('#cities').innerHTML = '';
  CITIES.forEach(c => {
    const b = document.createElement('button'); b.type = 'button'; b.className = 'city'; b.textContent = c.name; b.disabled = !c.ready; b.setAttribute('aria-pressed', c.id === city ? 'true' : 'false');
    b.onclick = () => { if (c.id !== city) pickRoute(ROUTES.find(r => r.city === c.id).id); }; // another city: its first route
    $('#cities').appendChild(b);
  });
  const box = $('#routes'); box.innerHTML = '';
  ROUTES.filter(r => r.city === city).forEach(r => {
    const b = document.createElement('button'); b.type = 'button'; b.className = 'route'; b.setAttribute('aria-pressed', r.id === routeSel ? 'true' : 'false');
    const cv = document.createElement('canvas'); const T = sparkline(cv, r);
    const pb = Records.best(r.id);
    b.innerHTML = '<b></b><span class="meta"></span><span class="desc"></span>';
    b.querySelector('b').textContent = r.name;
    b.querySelector('.meta').textContent = t('route.meta', { d: fmt1(T.L / 1000), g: Math.round(T.gain) }) + (r.loop ? ', ' + t('route.loop') : '') + (r.osm ? ', ' + t('route.osm') : '') + (pb ? ', ' + t('route.record', { t: fmtTime(pb) }) : '');
    const sights = nearLandmarks(T).filter(l => l.dist <= 700).map(l => l.name); b.querySelector('.desc').textContent = r.desc + (sights.length ? t('route.sights', { list: sights.join(', ') }) : ''); b.appendChild(cv);
    b.onclick = () => pickRoute(r.id);
    box.appendChild(b);
  });
  renderStartSum();
}
function readSettings() {
  settings.circ = +$('#circ').value; settings.trainer = $('#trainer').value;
  settings.mass = clamp(+$('#mass').value || 75, 35, 160); settings.height = clamp(Math.round(+$('#height').value || 178), 120, 220); settings.bikeType = BIKE_TYPES[$('#bikeType').value] ? $('#bikeType').value : 'road'; settings.bikeKg = Math.round(clamp(+$('#bikeKg').value || bikeType().kg, 5, 30) * 10) / 10; settings.bots = +$('#bots').value; settings.level = $('#level').value; settings.difficulty = +$('#difficulty').value; settings.hrmax = clamp(+$('#hrmax').value || 185, 120, 230); settings.view = $('#view').value; settings.cadSpeed = $('#cadSpeed').value;
  store.set('settings', settings);
}
function fillSettings() { $('#circ').value = settings.circ; $('#trainer').value = settings.trainer; $('#mass').value = settings.mass; $('#height').value = settings.height || 178; $('#bikeType').innerHTML = Object.keys(BIKE_TYPES).map(k => '<option value="' + k + '">' + BIKE_TYPES[k].name + ', ≈' + fmt1(BIKE_TYPES[k].kg) + ' ' + t('u.kg') + '</option>').join(''); $('#bikeType').value = BIKE_TYPES[settings.bikeType] ? settings.bikeType : 'road'; $('#bikeKg').value = settings.bikeKg || bikeType().kg; renderBodyHint(); $('#bots').value = settings.bots; $('#level').value = settings.level; $('#difficulty').value = settings.difficulty; $('#hrmax').value = settings.hrmax; $('#view').value = settings.view; $('#cadSpeed').value = settings.cadSpeed || 'direct'; }
function showLoading(on) { $('#loading').classList.toggle('hidden', !on); }
