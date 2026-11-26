'use strict';
/* ---------------- Состояние заезда ---------------- */
function bikeType() { return BIKE_TYPES[settings.bikeType] || BIKE_TYPES.road; }
function kitted(ch) { return Object.assign({}, ch, KITS.ubt.over, { size: (settings.height || 178) / 178, tire: bikeType().tire }); } // размер модели — по росту
function renderBodyHint() {
  const el = $('#bodyHint'); if (!el) return; const h = settings.height || 178, m = settings.mass || 75, a = riderAero(h, m), bt = bikeType(), bk = settings.bikeKg || bt.kg, cda = a.CdA * bt.aero, bmi = m / Math.pow(h / 100, 2);
  el.textContent = t('body.hint', { a: numF(a.A, 2), cda: numF(cda, 3), total: fmt1(m + bk), bike: lc(bt.name), kg: fmt1(bk) }) + (bmi < 15 || bmi > 45 ? t('body.check') : '');
} // игрок всегда в форме UBT
let paused = false, photo = false, demoP = 150;
let routeSel = store.get('route', null);
if (!ROUTES.some(r => r.id === routeSel)) routeSel = ROUTES[0].id; // the first visit, or a route no map has any more
const settings = Object.assign({ circ: 2105, trainer: 'fluid', ring: 50, mass: 75, bots: 6, level: 'mid', look: 'bodycam', difficulty: 50, hrmax: 185, view: 'chase', char: 'me', wind: { on: false, from: 0, ms: 5 } }, store.get('settings', {}));
// the wind the settings ask for, { ms, from }, or none; the words for it: "5 m/s from the north"
const ownWind = () => settings.wind && settings.wind.on && settings.wind.ms > 0 ? { ms: settings.wind.ms, from: settings.wind.from || 0 } : null;
const windFrom = (from, lang = LANG) => [t('wind.n', null, lang), t('wind.ne', null, lang), t('wind.e', null, lang), t('wind.se', null, lang), t('wind.s', null, lang), t('wind.sw', null, lang), t('wind.w', null, lang), t('wind.nw', null, lang)][Math.round((from || 0) / 45) % 8];
const windWords = w => t('wind.sum', { ms: Math.round(w.ms), from: windFrom(w.from) }); // whole m/s, as it is set
if (!settings.viewDefault3) { settings.view = 'chase'; settings.viewDefault3 = true; } // стандартный вид — от третьего лица
// #471: a cadence sensor alone rides by the physics by default, once for everyone: the gear's speed was the default
// and is kept by whoever picks it again
if (!settings.cadPhysics) { settings.cadSpeed = 'physics'; settings.cadPhysics = true; }
settings.char = 'me'; // выбор героев убран: игрок всегда в форме UBT

function spawnBots(n, levelKey, s0) {
  bots.forEach(removeRiderModel); bots = [];
  const lv = LEVELS[levelKey] || LEVELS.mid, W = world.route.width, pool = CHARS.filter(c => c.id !== settings.char);
  for (let i = 0; i < n; i++) {
    const ch = pool[i % pool.length];
    const b = newRider(ch.name, ch.a, ch.mass, s0 - 3 - (i % 4) * 2.2, clamp(1.2 + (i % 3) * 1.6 + Math.random() * .4, .8, W / 2 - 1));
    b.ch = ch; b.wkg = lv[0] + (lv[1] - lv[0]) * (i + Math.random()) / Math.max(1, n); b.seed = Math.random() * 100;
    addRiderModel(b, ch); bots.push(b);
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
  bots.forEach(removeRiderModel); bots = [];
  me = newRider(t('you'), kitted(charById(settings.char)).a, settings.mass, 0, 2.6);
  applyLook('clean'); setView(settings.view, true); renderStartSum();
  groupRide = null; rideMode = settings.mode; MP.resultsFor = null; $('#btnPhoto').classList.remove('hidden'); if (MP.status === 'on') mpSchedule(300); renderMP();
}
function renderStartSum() {
  const el = $('#startSum'); if (!el) return;
  const r = ROUTES.find(x => x.id === routeSel) || ROUTES[0];
  const mode = (typeof MP !== 'undefined' && mpMyGroup()) ? t('sum.group') : settings.mode === 'plan' ? planSummary() : settings.mode === 'free' ? t('where.free') : +settings.bots ? t('sum.raceBots', { n: settings.bots }) : t('sum.raceAlone');
  const sm = Sensors.mode(), dev = sm === 'demo' ? t('sum.demo') : sm === 'power' ? t('sum.power') : sm === 'speed' ? t('sum.speed') : t('sum.cadence');
  el.innerHTML = '<b></b><span></span>'; el.querySelector('b').textContent = r.name;
  const w = (typeof MP !== 'undefined' && mpMyGroup()) ? null : ownWind();
  el.querySelector('span').textContent = mode[0].toUpperCase() + mode.slice(1) + ', ' + dev + (Sensors.live('hr').length ? ', ' + t('sum.hr') : '') + ', ' + lc(bikeType().name) + ' ' + fmt1(settings.bikeKg || bikeType().kg) + ' ' + t('u.kg') + (w ? ', ' + windWords(w) : '') + '.';
  if (heavyRoute(r) && matchMedia('(pointer: coarse)').matches) { const n = document.createElement('small'); n.className = 'heavy'; n.textContent = t('route.heavy'); el.appendChild(n); }
}
// A route this full of buildings and streets may draw slowly on a phone, which is told so (specs/495-virtual-race):
// Granfondo 2026, the Medeu climb and the centre's loop have 1000 to 1400 of them, the others under 700
const HEAVY_SCENERY = 800, heavyRoute = r => (r.buildings || []).length + (r.roads || []).length > HEAVY_SCENERY;
// страница 2: заезд
function startRace() {
  readSettings();
  rideMode = groupRide ? 'race' : settings.mode;
  rideWind = groupRide ? groupRide.wind : ownWind(); // in a group race, its host's: everyone in it rides in one air
  const route = ROUTES.find(r => r.id === routeSel);
  showLoading(true);
  setTimeout(() => {
    $('#gl').classList.remove('hidden'); onResize();
    if (!world || world.route.id !== route.id) buildWorld(route);
    world.lms.forEach(l => { l.done = false; });
    me = startRider(newRider(t('you'), kitted(charById(settings.char)).a, settings.mass, world.S0, keepLane(route.width)));
    const bt = bikeType(); me.CdA = riderAero(settings.height, settings.mass).CdA * bt.aero; me.bike = settings.bikeKg || bt.kg; me.Crr = bt.crr;
    // a race with protocols: the rider's bib and category, and their category's laps on a loop
    const rules = groupRide && groupRide.race, mine = rules && rules.me;
    world.FIN = world.T.loop && mine ? world.S0 + mine.laps * world.T.L : world.FIN1;
    me.bib = mine ? mine.bib : ''; me.group = mine ? mine.group : ''; setBib(playerAvatar, me.bib);
    stravaShow(null, null); intervalsShow(null, null);
    const planMode = rideMode === 'plan', freeMode = rideMode === 'free';
    spawnBots(planMode || freeMode || groupRide ? 0 : +settings.bots, settings.level, world.S0);
    Work.active = false;
    const plan = planMode ? planToRide() : null, first = plan && plan.steps[0];
    if (plan) Work.start(plan.steps, plan.cues, plan.name);
    // the own plan starts on its first step's gear; any other ride, a workout by power too, on a middle one
    if (first && first.f != null) { gearF = first.f; gearR = first.r; } else { gearF = bikeF().length; gearR = Math.ceil(bikeR().length / 2); }
    $('#planList').classList.toggle('hidden', !planMode); $('#target').classList.toggle('hidden', !planMode); planListIdx = -2;
    $('#btnFinish').classList.toggle('hidden', !(planMode || freeMode));
    $('#pauseHint').textContent = freeMode ? t('pause.free') : planMode ? t('pause.plan') : t('pause.race');
    if (freeMode) setTimeout(() => toast(t('toast.free'), 5), 4500);
    if (groupRide) { $('#pauseHint').textContent = t('pause.group'); setTimeout(() => toast(me.bib ? t('toast.race', { bib: me.bib }) : t('toast.group'), 4), 300); }
    $('#btnPhoto').classList.toggle('hidden', !!groupRide);
    raceT = 0; cdT = groupRide ? Math.max(.5, (groupRide.startAt - Date.now()) / 1000) : 3.999; phase = 'countdown'; paused = false;
    $('#menu').classList.add('hidden'); $('#hud').classList.remove('hidden'); $('#count').classList.remove('hidden');
    applyLook('clean'); setView(settings.view, true); Trainer.sent = Trainer.held = null; drawProfileBase(); updateModeUI(); showLoading(false);
    last = performance.now(); // the next frame counts from here: the time the course took to build is not the countdown's
    try { navigator.wakeLock && navigator.wakeLock.request('screen').catch(() => {}); } catch (e) {}
  }, 30);
}
function finishRace() {
  phase = 'done';
  const t = me.finishT, st = me.stats, distKm = (world.FIN - world.S0) / 1000;
  const list = raceList(), place = list.findIndex(x => x.me) + 1, humans = list.filter(x => x.human).length;
  const avgP = Math.round(st.sumP / Math.max(1, st.t));
  const ride = { id: Date.now().toString(36), date: Date.now(), route: world.route.id, time: Math.round(t * 10) / 10, dist: Math.round(distKm * 100) / 100, avgSpeed: Math.round(distKm / (t / 3600) * 10) / 10, avgPower: avgP, real: st.real, demo: st.demoT > st.t * .5, maxSpeed: Math.round(st.maxV * 36) / 10, gain: Math.round(st.gain), avgCad: st.nCad ? Math.round(st.sumCad / st.nCad) : null, avgHR: st.nHR ? Math.round(st.sumHR / st.nHR) : null, place, of: list.length, char: settings.char, group: !!groupRide, wind: rideWind };
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
