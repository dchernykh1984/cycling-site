'use strict';
/* ---------------- HUD ---------------- */
let hudAcc = 0, toastT = 0;
function toast(t, dur) { const el = $('#toast'); el.textContent = t; el.classList.add('show'); toastT = dur || 2.5; }
function gradeColor(g) { const p = g * 100; if (p < -1.5) return 'rgba(61,123,182,.85)'; if (p < 2) return 'rgba(76,124,85,.85)'; if (p < 5) return 'rgba(214,160,40,.88)'; if (p < 8) return 'rgba(214,110,40,.9)'; return 'rgba(195,50,59,.92)'; }
let profBase = null;
function drawProfileBase() {
  const cv = $('#profile'); if (!cv || !world) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2), w = cv.clientWidth || 300, h = cv.clientHeight || 60;
  cv.width = w * dpr; cv.height = h * dpr; profBase = document.createElement('canvas'); profBase.width = cv.width; profBase.height = cv.height;
  const g = profBase.getContext('2d'), T = world.T, a = world.S0, b = world.FIN, o = {};
  let mn = 1e9, mx = -1e9; const ys = [];
  for (let i = 0; i <= 200; i++) { const y = sampleAt(T, a + (b - a) * i / 200, o).y; ys.push(y); mn = Math.min(mn, y); mx = Math.max(mx, y); }
  const rng2 = Math.max(30, mx - mn); world.prof = { mn, rng: rng2 };
  g.beginPath(); g.moveTo(0, cv.height);
  ys.forEach((y, i) => g.lineTo(i / 200 * cv.width, cv.height - 6 * dpr - (y - mn) / rng2 * (cv.height - 14 * dpr)));
  g.lineTo(cv.width, cv.height); g.closePath(); g.fillStyle = 'rgba(243,246,249,.22)'; g.fill();
  g.lineWidth = 1.5 * dpr; g.strokeStyle = 'rgba(243,246,249,.85)'; g.beginPath(); ys.forEach((y, i) => { const X = i / 200 * cv.width, Y = cv.height - 6 * dpr - (y - mn) / rng2 * (cv.height - 14 * dpr); i ? g.lineTo(X, Y) : g.moveTo(X, Y); }); g.stroke();
  g.fillStyle = 'rgba(243,246,249,.7)'; g.font = (11 * dpr) + 'px Golos Text, sans-serif'; g.fillText(Math.round(mx) + ' ' + t('u.m'), 6 * dpr, 13 * dpr); g.fillText(Math.round(mn) + ' ' + t('u.m'), 6 * dpr, cv.height - 4 * dpr);
}
function drawProfile() {
  const cv = $('#profile'); if (!profBase) return; const g = cv.getContext('2d'), dpr = cv.width / (cv.clientWidth || 1);
  g.clearRect(0, 0, cv.width, cv.height); g.drawImage(profBase, 0, 0);
  const span = world.FIN - world.S0, pr = world.prof, o = {};
  const mark = (R, c, r) => { const rel = R.s - world.S0, f = rideMode !== 'race' && world.T.loop ? (((rel % span) + span) % span) / span : clamp(rel / span, 0, 1), y = sampleAt(world.T, R.s, o).y; const X = f * cv.width, Y = cv.height - 6 * dpr - (y - pr.mn) / pr.rng * (cv.height - 14 * dpr); g.fillStyle = c; g.beginPath(); g.arc(X, Y, r * dpr, 0, 7); g.fill(); };
  bots.forEach(b => mark(b, '#' + b.color.toString(16).padStart(6, '0'), 3));
  mark(me, '#ffffff', 6); mark(me, '#C3323B', 4);
}
function drawMini() {
  const cv = $('#mini'), g = cv.getContext('2d'), T = world.T, W = cv.width, H = cv.height;
  g.clearRect(0, 0, W, H);
  const sx = T.maxX - T.minX, sz = T.maxZ - T.minZ, sc = (W - 40) / Math.max(sx, sz), ox = (W - sx * sc) / 2, oz = (H - sz * sc) / 2;
  const P = (x, z) => [ox + (x - T.minX) * sc, oz + (z - T.minZ) * sc];
  g.lineWidth = 6; g.strokeStyle = 'rgba(243,246,249,.35)'; g.lineCap = 'round'; g.lineJoin = 'round'; g.beginPath();
  for (let i = 0; i < T.N; i += 4) { const p = P(T.X[i], T.Z[i]); i ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1]); } g.stroke();
  const o = {};
  bots.forEach(b => { sampleAt(T, b.s, o); const p = P(o.x, o.z); g.fillStyle = '#' + b.color.toString(16).padStart(6, '0'); g.beginPath(); g.arc(p[0], p[1], 6, 0, 7); g.fill(); });
  sampleAt(T, me.s, o); const p = P(o.x, o.z);
  g.fillStyle = '#fff'; g.beginPath(); g.arc(p[0], p[1], 11, 0, 7); g.fill(); g.fillStyle = '#C3323B'; g.beginPath(); g.arc(p[0], p[1], 8, 0, 7); g.fill();
  world.lms.forEach(l => { if (l.dist > 700) return; const q = P(l.x, l.z); if (q[0] < 0 || q[1] < 0 || q[0] > W || q[1] > H) return; g.save(); g.translate(q[0], q[1]); g.rotate(Math.PI / 4); g.fillStyle = '#E5A23A'; g.fillRect(-6, -6, 12, 12); g.restore(); });
  g.fillStyle = 'rgba(243,246,249,.6)'; g.font = '600 18px Golos Text, sans-serif'; g.fillText(t('map.north'), W - 26, 24);
}
function updateHUD(inp, grade) {
  const T = world.T, spd = me.v * 3.6;
  $('#vSpeed').textContent = Math.round(spd);
  $('#uSpeed').textContent = inp.direct ? t('u.kmh') + ', ' + gearLabel(gearF, gearR) : t('u.kmh');
  $('#vPower').textContent = Math.round(inp.P);
  $('#vCad').textContent = inp.cad != null && inp.cad > 0 ? Math.round(inp.cad) : (inp.mode === 'speed' ? '—' : '0');
  $('#vGrade').textContent = fmtPct(grade * 100);
  const tg = Trainer.info(); $('#uGrade').textContent = tg != null ? t('hud.onTrainer', { p: fmtPct(tg) }) : t('hud.grade');
  const hr = Sensors.hr(), hb = $('#hrBox'); hb.classList.toggle('hidden', hr == null);
  if (hr != null) { const z = hrZone(hr); $('#vHR').textContent = hr; $('#uHR').textContent = t('hud.hrZone', { z }); hb.style.background = ZONE_BG[z]; }
  $('#grade').style.background = gradeColor(grade);
  $('#vTime').textContent = fmtTime(raceT);
  const done = clamp(me.s - world.S0, 0, world.FIN - world.S0);
  $('#vDist').textContent = rideMode !== 'race' ? t('hud.lap', { d: fmt1(me.stats.dist / 1000), lap: me.lap + 1 }) : t('hud.of', { d: fmt1(done / 1000), total: fmt1((world.FIN - world.S0) / 1000) });
  if (rideMode === 'plan') updatePlanHUD(inp.cad);
  $('#vEle').textContent = t('hud.ele', { m: Math.round(sampleAt(T, me.s, {}).y) });
  const all = [me].concat(bots).slice().sort((a, b) => (b.finishT != null ? 1e9 - b.finishT : b.s) - (a.finishT != null ? 1e9 - a.finishT : a.s));
  const lead = all[0];
  $('#boardList').innerHTML = all.slice(0, 8).map((r, i) => { const gap = r === lead ? '' : '+' + Math.max(0, Math.round((lead.s - r.s) / Math.max(r.v, 3))) + ' ' + t('u.s'); const col = r === me ? '#fff' : '#' + r.color.toString(16).padStart(6, '0'); return '<li class="' + (r === me ? 'me' : '') + '"><span class="dot" style="background:' + col + '"></span><span>' + escapeHTML(r.name) + '</span><span class="gap">' + gap + '</span></li>'; }).join('');
  drawMini(); drawProfile();
  updateTagText();
}
