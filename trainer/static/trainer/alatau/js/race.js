'use strict';
/* ---------------- Состояние заезда ---------------- */
function bikeType() { return BIKE_TYPES[settings.bikeType] || BIKE_TYPES.road; }
function kitted(ch) { return Object.assign({}, ch, KITS.ubt.over, { size: (settings.height || 178) / 178, tire: bikeType().tire }); } // размер модели — по росту
// Аэродинамика по росту и весу: лобовая площадь гонщика с велосипедом (формула Бассетта и соавт., 1999)
// A = 0,0293 · рост(м)^0,725 · вес(кг)^0,425 + 0,0604; CdA = 0,88 · A (посадка с руками на тормозных ручках)
function riderAero(hcm, kg) { const A = 0.0293 * Math.pow((hcm || 178) / 100, .725) * Math.pow(kg || 75, .425) + .0604; return { A, CdA: A * .88 }; }
function renderBodyHint() {
  const el = $('#bodyHint'); if (!el) return; const h = settings.height || 178, m = settings.mass || 75, a = riderAero(h, m), bt = bikeType(), bk = settings.bikeKg || bt.kg, cda = a.CdA * bt.aero, bmi = m / Math.pow(h / 100, 2);
  el.textContent = t('body.hint', { a: numF(a.A, 2), cda: numF(cda, 3), total: fmt1(m + bk), bike: lc(bt.name), kg: fmt1(bk) }) + (bmi < 15 || bmi > 45 ? t('body.check') : '');
} // игрок всегда в форме UBT
function styleMult(b, grade) {
  switch (b.ch.style) {
    case 'climber': return grade > .03 ? 1.13 : .96;
    case 'sprinter': return world.FIN - b.s < 450 ? 1.32 : .97;
    case 'rouleur': return Math.abs(grade) < .02 ? 1.06 : .97;
    case 'attacker': return ((clockT + b.seed * 9) % 90) < 16 ? 1.27 : .95;
    default: return 1;
  }
}
const LEVELS = { easy: [1.8, 2.4], mid: [2.5, 3.2], hard: [3.3, 4.2] };
let phase = 'loading', bots = [], me = null, raceT = 0, cdT = 0, paused = false, photo = false, demoP = 150, cogIdx = 5;
let routeSel = store.get('route', 'center');
const settings = Object.assign({ circ: 2105, trainer: 'fluid', ring: 50, mass: 75, bots: 6, level: 'mid', look: 'bodycam', difficulty: 50, hrmax: 185, view: 'chase', char: 'me' }, store.get('settings', {}));
if (!settings.viewDefault3) { settings.view = 'chase'; settings.viewDefault3 = true; } // стандартный вид — от третьего лица
settings.char = 'me'; // выбор героев убран: игрок всегда в форме UBT

function newRider(name, color, mass, s, lane) { return { name, color, mass, v: 0, s, lane, CdA: PHYS.CdA, phase: Math.random() * 6, finishT: null, P: 0 }; }
function spawnBots(n, levelKey, s0) {
  bots.forEach(b => scene.remove(b.mesh.g)); bots = [];
  const lv = LEVELS[levelKey] || LEVELS.mid, W = world.route.width, pool = CHARS.filter(c => c.id !== settings.char);
  for (let i = 0; i < n; i++) {
    const ch = pool[i % pool.length];
    const b = newRider(ch.name, ch.a, ch.mass, s0 - 3 - (i % 4) * 2.2, clamp(1.2 + (i % 3) * 1.6 + Math.random() * .4, .8, W / 2 - 1));
    b.ch = ch; b.wkg = lv[0] + (lv[1] - lv[0]) * (i + Math.random()) / Math.max(1, n); b.seed = Math.random() * 100;
    b.mesh = makeRider(ch); scene.add(b.mesh.g); bots.push(b);
  }
}
function setPlayerChar(id) {
  settings.char = charById(id).id;
  if (playerAvatar) scene.remove(playerAvatar.g);
  playerAvatar = makeRider(kitted(charById(settings.char))); playerAvatar.g.visible = false; scene.add(playerAvatar.g);
  if (me) me.color = kitted(charById(settings.char)).a;
}
/* превью персонажа в меню */
let prev = null;
function initPreview() {
  const cv = $('#charPrev'); if (!cv) return;
  try {
    const r = new THREE.WebGLRenderer({ canvas: cv, antialias: true, alpha: true }); r.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    const sc = new THREE.Scene(); sc.add(new THREE.HemisphereLight(0xe6efff, 0x6a5e4c, .85)); const dl = new THREE.DirectionalLight(0xfff2dc, .9); dl.position.set(-2, 3, 2); sc.add(dl);
    const disc = new THREE.Mesh(new THREE.CircleGeometry(1.1, 40), new THREE.MeshLambertMaterial({ color: 0x9aa3ab })); disc.rotation.x = -Math.PI / 2; sc.add(disc);
    const c = new THREE.PerspectiveCamera(30, 1, .1, 50); c.position.set(3.1, 1.65, 3.45); c.lookAt(0, .88, 0);
    prev = { r, sc, c, model: null, rot: -.6, ph: 0 };
  } catch (e) { cv.classList.add('hidden'); }
}
function setPreview(id) {
  if (!prev) return; if (prev.model) prev.sc.remove(prev.model.g);
  prev.model = makeRider(kitted(charById(id))); prev.sc.add(prev.model.g);
}
function renderPreview(dt) {
  if (!prev || !prev.model) return; const cv = prev.r.domElement, w = cv.clientWidth, h = cv.clientHeight; if (!w || !h) return;
  if (cv.width !== Math.round(w * prev.r.getPixelRatio())) { prev.r.setSize(w, h, false); prev.c.aspect = w / h; prev.c.updateProjectionMatrix(); }
  prev.rot += dt * .45; prev.ph += dt * 8; prev.model.g.rotation.y = prev.rot; poseRider(prev.model, prev.ph); prev.r.render(prev.sc, prev.c);
}
function renderChars() {} // выбор героев убран
function startMenu() { // страница 1: настройки (3D-сцена скрыта и не рисуется)
  phase = 'menu'; paused = false; photo = false;
  $('#menu').classList.remove('hidden'); $('#gl').classList.add('hidden'); $('#hud').classList.add('hidden'); $('#count').classList.add('hidden');
  $('#resM').classList.add('hidden'); $('#pauseM').classList.add('hidden'); $('#photoUI').classList.add('hidden'); $('#stamp').classList.add('hidden');
  bots.forEach(b => scene.remove(b.mesh.g)); bots = [];
  me = newRider(t('you'), kitted(charById(settings.char)).a, settings.mass, 0, 2.6);
  applyLook('clean'); setView(settings.view, true); renderStartSum();
  groupRide = null; rideMode = settings.mode; MP.resultsFor = null; $('#btnPhoto').classList.remove('hidden'); if (MP.status === 'on') mpSchedule(300); renderMP();
}
function renderStartSum() {
  const el = $('#startSum'); if (!el) return;
  const r = ROUTES.find(x => x.id === routeSel) || ROUTES[0];
  const mode = (typeof MP !== 'undefined' && mpMyGroup()) ? t('sum.group') : settings.mode === 'plan' ? t('sum.plan', { t: fmtTime(planTotalMin() * 60) }) : settings.mode === 'free' ? t('where.free') : +settings.bots ? t('sum.raceBots', { n: settings.bots }) : t('sum.raceAlone');
  const sm = Sensors.mode(), dev = sm === 'demo' ? t('sum.demo') : sm === 'power' ? t('sum.power') : sm === 'speed' ? t('sum.speed') : t('sum.cadence');
  el.innerHTML = '<b></b><span></span>'; el.querySelector('b').textContent = r.name;
  el.querySelector('span').textContent = mode[0].toUpperCase() + mode.slice(1) + ', ' + dev + (Sensors.live('hr').length ? ', ' + t('sum.hr') : '') + ', ' + lc(bikeType().name) + ' ' + fmt1(settings.bikeKg || bikeType().kg) + ' ' + t('u.kg') + '.';
}
// страница 2: заезд
function startRace() {
  readSettings();
  rideMode = groupRide ? 'race' : settings.mode;
  const route = ROUTES.find(r => r.id === routeSel);
  showLoading(true);
  setTimeout(() => {
    $('#gl').classList.remove('hidden'); onResize();
    if (!world || world.route.id !== route.id) buildWorld(route);
    world.lms.forEach(l => { l.done = false; });
    me = newRider(t('you'), kitted(charById(settings.char)).a, settings.mass, world.S0, Math.min(3.2, route.width / 2 - 1.5));
    const bt = bikeType(); me.CdA = riderAero(settings.height, settings.mass).CdA * bt.aero; me.bike = settings.bikeKg || bt.kg; me.Crr = bt.crr;
    me.stats = { dist: 0, gain: 0, sumP: 0, sumCad: 0, nCad: 0, maxV: 0, t: 0, sumHR: 0, nHR: 0, maxHR: 0, real: false, demoT: 0 };
    me.powerLog = []; me.pAcc = 0; me.pT = 0; me.track = []; stravaShow(null, null);
    const planMode = rideMode === 'plan', freeMode = rideMode === 'free';
    spawnBots(planMode || freeMode || groupRide ? 0 : +settings.bots, settings.level, world.S0);
    me.lap = 0; Work.active = false;
    if (planMode) { Work.start(settings.plan.steps); gearF = settings.plan.steps[0].f; gearR = settings.plan.steps[0].r; }
    else { gearF = bikeF().length; gearR = Math.ceil(bikeR().length / 2); }
    $('#planBox').classList.toggle('hidden', !planMode); $('#board').classList.toggle('hidden', planMode || freeMode);
    $('#btnFinish').classList.toggle('hidden', !(planMode || freeMode));
    $('#pauseHint').textContent = freeMode ? t('pause.free') : planMode ? t('pause.plan') : t('pause.race');
    if (freeMode) setTimeout(() => toast(t('toast.free'), 5), 4500);
    if (groupRide) { $('#pauseHint').textContent = t('pause.group'); setTimeout(() => toast(t('toast.group'), 4), 300); }
    $('#btnPhoto').classList.toggle('hidden', !!groupRide);
    raceT = 0; cdT = groupRide ? Math.max(.5, (groupRide.startAt - Date.now()) / 1000) : 3.999; phase = 'countdown'; paused = false;
    $('#menu').classList.add('hidden'); $('#hud').classList.remove('hidden'); $('#count').classList.remove('hidden');
    applyLook('clean'); setView(settings.view, true); Trainer.sent = null; drawProfileBase(); updateModeUI(); showLoading(false);
    try { navigator.wakeLock && navigator.wakeLock.request('screen').catch(() => {}); } catch (e) {}
  }, 30);
}
function finishRace() {
  phase = 'done';
  const t = me.finishT, st = me.stats, distKm = (world.FIN - world.S0) / 1000;
  const list = raceList(), place = list.findIndex(x => x.me) + 1, humans = list.filter(x => x.human).length;
  const avgP = Math.round(st.sumP / Math.max(1, st.t));
  const ride = { id: Date.now().toString(36), date: Date.now(), route: world.route.id, time: Math.round(t * 10) / 10, dist: Math.round(distKm * 100) / 100, avgSpeed: Math.round(distKm / (t / 3600) * 10) / 10, avgPower: avgP, real: st.real, demo: st.demoT > st.t * .5, maxSpeed: Math.round(st.maxV * 36) / 10, gain: Math.round(st.gain), avgCad: st.nCad ? Math.round(st.sumCad / st.nCad) : null, avgHR: st.nHR ? Math.round(st.sumHR / st.nHR) : null, place, of: list.length, char: settings.char, group: !!groupRide };
  const rec = Records.add(ride, me.powerLog || []), pb = rec.prev && rec.prev.time;
  $('#resTitle').textContent = place === 1 && bots.length ? (groupRide ? tr('res.winGroup') : tr('res.win')) : tr('res.finish');
  $('#resSub').textContent = world.route.name + (bots.length ? tr('res.place', { p: place, n: list.length }) : '') + (pb && t >= pb ? tr('res.best', { t: fmtTime(pb) }) : '.') + (humans && list.some(x => x.human && x.est) ? tr('res.pending') : '');
  $('#resRec').innerHTML = rec.news.length ? '<b>' + tr('res.newRecords') + '</b><ul>' + rec.news.map(n => '<li>' + n + '</li>').join('') + '</ul>' : '';
  $('#resRec').classList.toggle('hidden', !rec.news.length);
  const sx = [[fmtTime(t), tr('res.time')], [fmt1(distKm / (t / 3600)), tr('res.avgKmh')], [avgP + ' ' + tr('u.w'), st.real ? tr('res.avgPower') : tr('res.avgPowerEst')], [st.nCad ? Math.round(st.sumCad / st.nCad) : '—', tr('res.avgCad')], [fmt1(st.maxV * 3.6), tr('res.maxKmh')], [Math.round(st.gain) + ' ' + tr('u.m'), tr('rec.gain')]];
  if (st.nHR) sx.push([Math.round(st.sumHR / st.nHR) + ' / ' + st.maxHR, tr('res.hr')]);
  $('#resStats').innerHTML = sx.map(s => '<div class="stat"><div class="v">' + s[0] + '</div><div class="u">' + s[1] + '</div></div>').join('');
  renderRaceList(list);
  if (groupRide) { const gid = groupRide.gid; setTimeout(() => mpPollResults(gid, Date.now() + 10 * 60000), 2500); }
  setTimeout(() => $('#resM').classList.remove('hidden'), 1500);
}
