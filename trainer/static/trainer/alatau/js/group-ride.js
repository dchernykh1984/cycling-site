'use strict';
/* ---------------- Совместная езда: лобби, групповые гонки и соперники онлайн ---------------- */
const MP = { status: 'connecting', online: [], groups: [], riders: [], offset: 0, busy: false, timer: null, started: new Set(), lastInp: null, resultsFor: null, linkShown: false, linkChecked: false, crossings: [] };
// a group race named by the link the page was opened with (?group=)
const LINKED = (g => /^[0-9]{1,12}$/.test(g || '') ? +g : null)(new URLSearchParams(location.search).get('group'));
// the address of a group race: the site's page that frames the trainer, which also hands a newcomer
// the cookie the page needs to join -- never the trainer page (alatau.html) on its own
function groupLink(id) {
  const page = Records.me && Records.me.page_url;
  let base = page ? location.origin + langPath(page) + '?' : location.origin + location.pathname + '?lang=' + LANG + '&';
  try { if (!page && window.top !== window) base = window.top.location.origin + window.top.location.pathname + '?'; } catch (e) {}
  return base + 'group=' + id;
}
function mpNote(text) { const el = $('#mpNote'); el.textContent = text; el.classList.toggle('hidden', !text); }
async function mpShare(g) {
  const url = groupLink(g.id);
  try {
    const title = (g.kind || 'race') === 'ride' ? t('mp.shareTitleRide', { route: routeTitle(g) }) : t('mp.shareTitle', { route: routeTitle(g) });
    if (navigator.share) { await navigator.share({ title, url }); return; }
    await navigator.clipboard.writeText(url); mpNote(t('mp.copied', { url }));
  } catch (e) { if (e.name !== 'AbortError') mpNote(t('mp.copyFailed', { url })); }
}
// A link names a ride or a race: a page set to a workout, which gathers neither, turns once to the mode that rides it
function mpFollowLink() {
  const g = LINKED && !MP.linkFollowed && settings.mode === 'plan' && MP.groups.find(x => x.id === LINKED);
  if (!g) return;
  MP.linkFollowed = true; settings.mode = (g.kind || 'race') === 'ride' ? 'free' : 'race'; saveSettings(); renderPlanEditor();
}
// a linked race that is not open any more says why, once
async function mpCheckLink() {
  if (!LINKED || MP.linkChecked || MP.groups.some(g => g.id === LINKED)) return;
  MP.linkChecked = true;
  try { const g = await Site.get('/groups/' + LINKED); mpNote(g.cancelled ? t('mp.linkCancelled') : t('mp.linkStarted')); }
  catch (e) { if (e.status === 404) mpNote(t('mp.linkMissing')); }
}
let groupRide = null;   // { gid, startAt, wind, race } во время групповой гонки; wind, { ms, from }, is its host's
// A race with protocols (specs/495-virtual-race) or a time trial: its event, mode and drafting rule, and what the member
// rides in it -- bib, group, laps and own start
const groupRules = g => g.event || g.mode === 'itt' ? { event: g.event || null, mode: g.mode, draftBetween: g.draft_between_groups !== false, me: g.me || null } : null;
// what block 3 gathers: the mode's -- a free ride's ride together, a race -- and nothing in a workout, ridden alone
const mpKind = () => settings.mode === 'race' ? 'race' : settings.mode === 'free' ? 'ride' : null;
// who may make a race an event with its registration: an organizer, as the event form lets them register riders
const mpOrganizes = () => !!(Records.me && Records.me.organizes);
// a crossing the ride reports (js/ride.js), `ago` seconds ago: queued with its race for the site, at the moment it
// happened on the site's clock, as a chronometer would take it -- a rider who started late carries the time they lost
function mpCrossing(point, last, ago) { MP.crossings.push({ gid: groupRide.gid, point, last, at_ms: Math.round(Date.now() + MP.offset - ago * 1000) }); }
const groupWind = g => g.wind_ms > 0 ? { ms: g.wind_ms, from: g.wind_from_deg || 0 } : null;
const MP_COLORS = [0x2f6db5, 0x3f8f5a, 0x7a4fb0, 0x1f9aa3, 0xb53f7a, 0xe5a23a, 0x5a6470, 0xd36b2c, 0x2c3e8f, 0x8fa33a];
const mpColor = id => MP_COLORS[Math.abs(+id || 0) % MP_COLORS.length];
const mpStartLocal = g => Date.parse(g.start_at) - MP.offset;   // время старта по своим часам
function mpInit() {
  if (!Records.synced) { MP.status = Records.me ? 'guest' : 'off'; renderMP(); return; }
  MP.status = 'on'; mpPoll();
}
// Block 3 by the mode: in a workout only why there is nothing to gather; else the button for the mode's kind, its
// hints, and a race's settings -- a gap between categories in a group race, an interval in a time trial
function renderRaceOpts() {
  const kind = mpKind(), ride = kind === 'ride', itt = $('#mpRaceMode').value === 'itt';
  $('#mpPlanNote').classList.toggle('hidden', kind !== null); $('#mpBody').classList.toggle('hidden', kind === null);
  $('#mpCreate').textContent = ride ? t('mp.createRide') : t('mp.create');
  $('#mpHint').textContent = ride ? t('mp.hintRide') : t('mp.hint');
  $('#mpEventHint').textContent = ride ? t('mp.eventHintRide') : t('mp.eventHint');
  $('#mpRaceOpts').classList.toggle('hidden', kind !== 'race');
  $('#mpRaceGapL').classList.toggle('hidden', itt); $('#mpRaceDraftL').classList.toggle('hidden', itt);
  $('#mpRaceIntervalL').classList.toggle('hidden', !itt); renderWhen();
}
function mpSchedule(ms) { clearTimeout(MP.timer); MP.timer = setTimeout(mpPoll, ms); }
async function mpPoll() {
  if (MP.status !== 'on') return;
  if (MP.busy) { mpSchedule(300); return; }
  MP.busy = true;
  const riding = phase !== 'menu' && world && me, inp = MP.lastInp || {};
  // a race with protocols: the crossings the site has not taken yet go with every call until one is answered, one
  // race's at a time -- the race ridden, else, in the menu, the one left over: a rider gone back at once still sends it
  const gid = riding ? (groupRide ? groupRide.gid : null) : (MP.crossings.length ? MP.crossings[0].gid : null);
  const sent = MP.crossings.filter(c => c.gid === gid).slice(0, 50), crossings = sent.map(c => ({ point: c.point, at_ms: c.at_ms, last: c.last }));
  const body = riding
    ? { status: 'ride', route: world.route.id, mode: rideMode, group_id: groupRide ? groupRide.gid : null, distance_m: Math.round(me.s * 10) / 10, speed_ms: Math.round(me.v * 100) / 100, cadence_rpm: Math.round(clamp(inp.cad || 0, 0, 250)), power_w: Math.round(clamp(inp.P || 0, 0, 3000)), lane_m: Math.round(me.lane * 10) / 10, finished_s: me.finishT != null ? Math.round(me.finishT * 10) / 10 : null, cda: Math.round(clamp(me.CdA || PHYS.CdA, .1, 1.2) * 1000) / 1000, crossings }
    : Object.assign({ status: 'lobby', route: routeSel }, sent.length ? { group_id: gid, crossings } : {});
  const t0 = Date.now();
  try {
    const res = await Site.post('/presence', body), t1 = Date.now();
    MP.crossings = MP.crossings.filter(c => !sent.includes(c));
    MP.offset = Date.parse(res.server_now) - (t0 + t1) / 2;
    MP.online = res.online || []; MP.riders = res.riders || []; MP.recv = t1;
    if (!riding) MP.groups = res.groups || [];
    if (phase === 'menu') { mpFollowLink(); mpMaybeStart(); renderMP(); mpCheckLink(); } else mpSyncRemotes();
  } catch (e) {
    if (e.status === 401 || e.status === 403) { MP.status = 'guest'; renderMP(); MP.busy = false; return; }
  }
  MP.busy = false;
  mpSchedule(phase === 'menu' ? 3000 : 1000);
}
// The hour a page waits for a race to start, and the least gap between one host's races (trainer/live.py). The race
// a page waits for is its member's first to start within the hour; one further ahead waits on its own, and a
// member joins any race that keeps the hour from theirs.
const MP_HOUR = 3600e3;
function mpMyGroup() { return MP.groups.find(g => g.is_member && mpStartLocal(g) - Date.now() < MP_HOUR); }
const mpClash = g => MP.groups.some(o => o.is_member && o.id !== g.id && Math.abs(Date.parse(o.start_at) - Date.parse(g.start_at)) < MP_HOUR);
// the start the menu asks for: { start_in_s }, or { start_at, at } at a date and time on the member's own clock, or
// null for a moment too soon, too far or not filled in
function mpWhen() {
  if ($('#mpDelay').value !== 'at') return { start_in_s: +$('#mpDelay').value || 60 };
  const at = new Date($('#mpDate').value + 'T' + $('#mpTime').value), ahead = at - Date.now();
  return isNaN(at) || ahead < 60e3 || ahead > 365 * 864e5 ? null : { start_at: at.toISOString(), at };
}
// a date and time to start from: the next whole hour but one, today or tomorrow
function renderWhen() {
  const at = $('#mpDelay').value === 'at', pad = n => String(n).padStart(2, '0'), day = d => d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
  // an event for a ride, by anyone; for a race, with its registration, by an organizer
  const offered = at && (mpKind() === 'ride' || (mpKind() === 'race' && mpOrganizes()));
  $('#mpWhen').classList.toggle('hidden', !at); ['#mpEventL', '#mpEventHint'].forEach(id => $(id).classList.toggle('hidden', !offered));
  if (at && !$('#mpDate').value) { const d = new Date(Date.now() + 2 * MP_HOUR); $('#mpDate').value = day(d); $('#mpTime').value = pad(d.getHours()) + ':00'; }
  $('#mpDate').min = day(new Date()); $('#mpDate').max = day(new Date(Date.now() + 365 * 864e5));
}
function mpMaybeStart() {
  const g = mpMyGroup(); if (!g || MP.started.has(g.id)) return;
  // in a time trial the rider's own start, their place in the start order after the race's
  const at = mpStartLocal(g) + ((g.me && g.me.start_offset_s) || 0) * 1000, now = Date.now();
  if (now >= at - 7000 && now < at + 30000) { MP.started.add(g.id); groupRide = { gid: g.id, startAt: at, wind: groupWind(g), race: groupRules(g), kind: g.kind || 'race' }; routeSel = g.route; renderMenu(); startRace(); }
}
async function mpAction(path, body) {
  try { await Site.post(path, body); } catch (e) { $('#mpStatus').textContent = t('mp.failed', { msg: e.message }); }
  mpSchedule(50);
}
// a ride or a race, as the mode gathers, on the chosen route in the host's wind, which is its riders'
function mpRace(when) {
  const r = ROUTES.find(x => x.id === routeSel) || ROUTES[0], w = ownWind(), kind = mpKind();
  // a race's mode, and the gaps and the drafting rule an event's registration gives categories to
  const race = kind === 'race' ? { mode: $('#mpRaceMode').value, group_gap_s: clamp(+$('#mpRaceGap').value || 0, 0, 3600), itt_interval_s: clamp(+$('#mpRaceInterval').value || 30, 5, 600), draft_between_groups: $('#mpRaceDraft').checked } : {};
  return Object.assign({ route: r.id, route_name: r.name, kind, loop: !!r.loop, wind_ms: w ? w.ms : 0, wind_from_deg: w ? w.from : 0 }, race, when.start_at ? { start_at: when.start_at } : { start_in_s: when.start_in_s });
}
function mpCreateGroup() {
  if (MP.status !== 'on' || !mpKind()) return;
  // at a date and time with "Add it to the calendar" ticked: the ride or race, and its event's form
  if (!$('#mpEventL').classList.contains('hidden') && $('#mpEvent').checked) { mpAddEvent(); return; }
  const when = mpWhen(); if (!when) { mpNote(t('mp.badTime')); return; }
  mpAction('/groups', mpRace(when));
}
// With the calendar box ticked: the ride or race at that date and time -- the member's own of that kind on this route
// at that minute, or a new one -- and the event form, filled from the route's template, for the member to check
async function mpAddEvent() {
  const when = mpWhen(); if (!when || !when.start_at) { mpNote(t('mp.badTime')); return; }
  if (MP.status !== 'on' || MP.eventBusy || !mpKind()) return;
  MP.eventBusy = true; $('#mpCreate').disabled = true; // one race and one form for one press
  try {
    const r = ROUTES.find(x => x.id === routeSel) || ROUTES[0];
    const kind = mpKind(), same = x => x.is_host && x.route === r.id && (x.kind || 'race') === kind && Math.abs(Date.parse(x.start_at) - when.at) < 60e3;
    const g = MP.groups.find(same) || await Site.post('/groups', mpRace(when));
    sendEventDraft(r, g, new Date(Date.parse(g.start_at)));
  } catch (e) { $('#mpStatus').textContent = t('mp.failed', { msg: e.message }); }
  MP.eventBusy = false; mpSchedule(50);
}
const LOCALES = { ru: 'ru-RU', kk: 'kk-KZ', en: 'en-GB' };
// The event's type and discipline by the English names every database has them under (calendar's draft): a virtual
// ride either way, a ride a coffee ride, a race a road race or a time trial by its mode
const EVENT_TYPES = ['Virtual Ride'];
const EVENT_DISCIPLINE = { ride: 'Coffee Ride', group: 'Road Race', itt: 'Individual Time Trial' };
// a race's registration as its event starts with it: men and women born from 1900 on, a loop's laps, the women's bibs
// and the men's -- each category as many riders as its bibs, the race all of them -- and a Strava link asked of each
const RACE_LAPS = 3, FIRST_BIRTH_YEAR = 1900, RACE_BIBS = { women: [1, 99], men: [100, 999] };
// the ride's or race's words in one language: its time on the member's clock with the clock's offset from UTC, the
// day, the link to it on the site's page in that language, the route -- its name, way with its length and climb, and
// finish -- its wind, the word on the button that joins it; a race's start and, on a loop, its laps
function eventWords(lang, r, g, at) {
  const loc = LOCALES[lang], T = buildTrack(r), off = -at.getTimezoneOffset(), abs = Math.abs(off);
  const zone = 'UTC' + (off ? (off > 0 ? '+' : '-') + Math.floor(abs / 60) + (abs % 60 ? ':' + String(abs % 60).padStart(2, '0') : '') : '');
  const page = Records.me.page_url.replace(/^\/(ru|kk|en)\//, '/' + lang + '/');
  const v = {
    time: at.toLocaleTimeString(loc, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }) + ' (' + zone + ')',
    date: at.toLocaleDateString(loc, { weekday: 'short', day: 'numeric', month: 'long' }),
    link: location.origin + page + '?group=' + g.id,
    km: (T.L / 1000).toLocaleString(loc, { minimumFractionDigits: 1, maximumFractionDigits: 1 }),
    climb: String(Math.round(T.gain)),
    wind: g.wind_ms > 0 ? t('mp.wind', { ms: Math.round(g.wind_ms), from: windFrom(g.wind_from_deg, lang) }, lang) : '',
    join: t('mp.join', null, lang),
    name: (r.names && r.names[lang]) || r.name
  };
  v.way = fillIn(r.event.way[lang], v); v.finish = r.event.finish[lang];
  if ((g.kind || 'race') === 'race') {
    v.how = g.mode === 'itt' ? t('ev.raceItt', { interval: g.itt_interval_s }, lang)
      : g.group_gap_s > 0 ? t('ev.raceGroupGap', { gap: g.group_gap_s }, lang) : t('ev.raceGroup', null, lang);
    v.laps = r.loop ? t('ev.raceLaps', null, lang) : '';
  }
  return v;
}
// a text's {placeholders} filled from v, each through `as` (escapeHTML for a description), an unknown one left
const fillIn = (text, v, as = x => x) => text.replace(/\{(\w+)\}/g, (m, k) => k in v ? as(v[k]) : m);
// the route as a GPX track for the event's map: its points, a loop's closed back at its start
function routeGpx(r) {
  const pts = r.loop ? r.pts.concat([r.pts[0]]) : r.pts;
  return '<?xml version="1.0" encoding="UTF-8"?>\n<gpx version="1.1" creator="' + escapeHTML(location.host) + '" xmlns="http://www.topografix.com/GPX/1/1"><trk><name>' + escapeHTML(r.name) + '</name><trkseg>'
    + pts.map(p => '<trkpt lat="' + p[0] + '" lon="' + p[1] + '"><ele>' + p[2] + '</ele></trkpt>').join('') + '</trkseg></trk></gpx>\n';
}
// The form the site keeps a draft from (calendar's SubmitDraftView), sent to the whole window: the words of a ride or a
// race in every language, the date of the start for the event's date, its type and discipline, the route's start
// as its venue in the virtual world, the route's track; for a race its registration with men and women and the race it is to hold
function sendEventDraft(r, g, at) {
  const form = document.createElement('form'), race = (g.kind || 'race') === 'race';
  form.method = 'post'; form.action = langPath(Records.me.event_draft_url); form.target = '_top';
  const put = (name, value) => { const i = document.createElement('input'); i.type = 'hidden'; i.name = name; i.value = value; form.appendChild(i); };
  const pad = n => String(n).padStart(2, '0');
  put('csrfmiddlewaretoken', Site.csrf()); put('date_start', at.getFullYear() + '-' + pad(at.getMonth() + 1) + '-' + pad(at.getDate()));
  Object.keys(LOCALES).forEach(lang => {
    const v = eventWords(lang, r, g, at), words = race
      ? [t('ev.raceTitle', null, lang), t('ev.racePreview', null, lang), t('ev.raceText', null, lang)]
      : [t('ev.rideTitle', null, lang), t('ev.ridePreview', null, lang), t('ev.rideText', null, lang)];
    put('title_' + lang, fillIn(words[0], v)); put('preview_text_' + lang, fillIn(words[1], v));
    put('description_' + lang, fillIn(words[2], v, escapeHTML));
  });
  EVENT_TYPES.forEach(n => put('event_type', n)); put('discipline', EVENT_DISCIPLINE[race ? g.mode : 'ride']);
  put('virtual_ride', g.id); // the ride or race the event is ridden in: its page opens it
  // its start in the virtual world, named after the route in each language, for the event's venue
  put('start_lat', r.pts[0][0]); put('start_lng', r.pts[0][1]); Object.keys(LOCALES).forEach(lang => put('route_name_' + lang, (r.names && r.names[lang]) || r.name));
  put('track_name', r.id); put('track_gpx', routeGpx(r));
  if (race) {
    const laps = r.loop ? RACE_LAPS : null, born = { birth_from: FIRST_BIRTH_YEAR, birth_to: new Date().getFullYear() };
    const bibs = ([a, b]) => ({ bib_from: a, bib_to: b, max_participants: b - a + 1 });
    const all = Object.values(RACE_BIBS).reduce((n, [a, b]) => n + b - a + 1, 0);
    put('registration', '1');
    put('categories', JSON.stringify([
      Object.assign({ name: t('ev.catMen'), male: true, female: false, laps }, born, bibs(RACE_BIBS.men)),
      Object.assign({ name: t('ev.catWomen'), male: false, female: true, laps }, born, bibs(RACE_BIBS.women))
    ]));
    put('birth_date_mode', 'year'); put('max_participants', all);
    put('additional_info_mode', 'strava'); put('additional_info_label', t('ev.stravaLink'));
    put('show_additional_info_in_list', '1'); put('additional_info_required', '1');
  }
  document.body.appendChild(form); form.submit(); form.remove();
}
// "Start" while waiting: the rider rides alone and the race goes on without them (a host hands it on)
async function mpLeaveMyGroup() { const g = mpMyGroup(); if (g) await mpAction('/groups/' + g.id + '/leave'); }

// живые соперники: те же записи, что у ботов, но без своей физики
function mpSyncRemotes() {
  if (!world || phase === 'menu') return;
  const want = new Map(MP.riders.filter(r => r.route === world.route.id).map(r => [r.user_id, r]));
  // кто пропал из ответа, остаётся на трассе ещё 20 с: связь у соседа могла просто запнуться
  const nowMs = performance.now();
  for (let i = bots.length - 1; i >= 0; i--) { const b = bots[i]; if (b.remote && !want.has(b.uid) && nowMs - (b.seenAt || 0) > 20000) { removeRiderModel(b); bots.splice(i, 1); } }
  let changedFinish = false;
  want.forEach((r, uid) => {
    let b = bots.find(x => x.remote && x.uid === uid);
    if (!b) {
      const col = mpColor(uid), ch = Object.assign({}, kitted(PLAYER_CH), { helmet: col, stripe: col });
      b = newRider(r.name || t('mp.rider'), col, 75, r.distance_m, clamp(r.lane_m || 2, .5, world.route.width / 2 - .8));
      Object.assign(b, { remote: true, uid, ch, seed: 0, wkg: 0, bib: r.bib || '' });
      addRiderModel(b, ch); bots.push(b);
    }
    // their drag area, for the wake they leave; their category and bib in a race with protocols
    b.CdA = r.cda || PHYS.CdA; b.group = r.group || '';
    if ((r.bib || '') !== (b.bib || '')) { b.bib = r.bib || ''; setBib(riderModels.get(b), b.bib); }
    b.seenAt = nowMs; b.sampleS = r.distance_m; b.sampleT = performance.now() - (r.age_s || 0) * 1000; b.v = r.speed_ms || 0; b.cad = r.cadence_rpm || 0; b.P = r.power_w || 0;
    b.lane = clamp(r.lane_m || b.lane, .5, world.route.width / 2 - .8); b.name = r.name || t('mp.rider');
    const f = typeof r.finished_s === 'number' ? r.finished_s : null; if (f !== b.finishT) { b.finishT = f; changedFinish = true; }
  });
  if (changedFinish && phase === 'done' && rideMode === 'race' && me.finishT != null && !MP.resultsFor) renderRaceList(raceList());
}
function mpStepRemote(b, dt) {
  const pred = b.sampleS + b.v * Math.min(2.5, (performance.now() - b.sampleT) / 1000);
  if (Math.abs(pred - b.s) > 60) b.s = pred; else b.s += (pred - b.s) * (1 - Math.exp(-dt * 4));
}
// итоги групповой гонки с сервера: время тех, кто финишировал, и тех, кто ещё едет
async function mpPollResults(gid, until) {
  if (phase !== 'done' || !groupRide || groupRide.gid !== gid || Date.now() > until) { MP.resultsFor = null; return; }
  MP.resultsFor = gid;
  try {
    const res = await Site.get('/groups/' + gid + '/results'), myId = Records.me && Records.me.user_id;
    const done = new Set(res.finished.map(f => f.user_id)), same = sameCategory();
    const list = res.finished.filter(f => same(f.group)).map(f => ({ name: f.user_id === myId ? t('you') : f.name, t: f.duration_s, me: f.user_id === myId, color: f.user_id === myId ? hexs(kitted(charById(settings.char)).a) : hexs(mpColor(f.user_id)), human: f.user_id !== myId }));
    if (!done.has(myId) && me.finishT != null) list.push({ name: t('you'), t: me.finishT, me: true, color: hexs(kitted(charById(settings.char)).a) });
    bots.filter(b => b.remote && !done.has(b.uid) && same(b.group)).forEach(b => list.push({ name: b.name, t: raceT + (world.FIN - b.s) / Math.max(b.v, 2), color: hexs(b.color), est: true, human: true }));
    list.sort((a, b) => a.t - b.t); renderRaceList(list);
    if (bots.some(b => b.remote && !done.has(b.uid))) setTimeout(() => mpPollResults(gid, until), 2000); else MP.resultsFor = null;
  } catch (e) { setTimeout(() => mpPollResults(gid, until), 5000); }
}
function renderMP() {
  const st = $('#mpStatus'); if (!st) return;
  const create = $('#mpCreate'), online = $('#mpOnline'), box = $('#mpGroups');
  online.innerHTML = '';
  if (MP.status !== 'on') {
    create.disabled = true; box.innerHTML = '';
    if (MP.status === 'guest') { st.innerHTML = escapeHTML(LINKED ? t('mp.guestLinked') : t('mp.guest')) + ' <a href="' + escapeHTML(Site.loginHref()) + '" target="_top">' + escapeHTML(t('signIn')) + '</a>'; }
    else st.textContent = MP.status === 'connecting' ? t('mp.connecting') : t('mp.offSite');
    renderStartSum(); return;
  }
  st.textContent = MP.online.length ? t('mp.others', { n: MP.online.length }) : t('mp.alone');
  MP.online.forEach(p => {
    const el = document.createElement('span'); el.className = 'mp-chip';
    const where = p.status === 'ride' ? (p.group_id ? t('where.group') : p.mode === 'free' ? t('where.free') : p.mode === 'plan' ? t('where.plan') : t('where.race')) + ': ' + routeName(p.route) : t('where.lobby');
    el.innerHTML = '<i></i><b></b><small></small>'; el.querySelector('i').style.background = hexs(mpColor(p.user_id));
    el.querySelector('b').textContent = p.name; el.querySelector('small').textContent = where;
    online.appendChild(el);
  });
  const mine = mpMyGroup();
  // cards are updated in place: rebuilt every second, they would swallow a tap landing mid-rebuild
  const ids = MP.groups.map(g => String(g.id));
  [...box.children].forEach(c => { if (!ids.includes(c.dataset.gid)) c.remove(); });
  MP.groups.forEach(g => {
    const left = Math.max(0, Math.ceil((mpStartLocal(g) - Date.now()) / 1000)), far = left * 1000 >= MP_HOUR;
    const when = far ? new Date(mpStartLocal(g)).toLocaleString(LOCALE, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }) : '';
    let card = box.querySelector('[data-gid="' + g.id + '"]');
    if (!card) {
      card = document.createElement('div'); card.dataset.gid = g.id;
      card.innerHTML = '<div><b></b><small></small></div><div class="mp-acts"><button class="btn act" type="button"></button><button class="btn share" type="button"></button></div>';
      box.appendChild(card);
    }
    card.className = 'mp-group' + (g.is_member ? ' on' : '') + (g.id === LINKED ? ' linked' : '');
    if (g.id === LINKED && !MP.linkShown) { MP.linkShown = true; card.scrollIntoView({ block: 'center' }); } // what the link named
    const ride = (g.kind || 'race') === 'ride';
    const who = g.is_host ? (ride ? t('mp.yoursRide') : t('mp.yours')) : ride ? t('mp.hostGathersRide', { name: g.host.name }) : t('mp.hostGathers', { name: g.host.name });
    card.querySelector('b').textContent = who + ': ' + routeTitle(g);
    const small = card.querySelector('small');
    small.textContent = (g.id === LINKED ? t('mp.byLink') : '') + (far ? t('mp.startsOn', { when }) : left ? t('mp.startsIn', { t: fmtTime(left) }) : t('mp.starting')) + t('mp.members', { list: g.members.map(m => ((Records.me && m.user_id === Records.me.user_id) ? t('youLower') : m.name) + (m.bib ? ' #' + m.bib : '')).join(', ') }) + (groupWind(g) ? t('mp.wind', { ms: Math.round(g.wind_ms), from: windFrom(g.wind_from_deg) }) : '');
    if (g.event) { // a race with protocols: its event, linked; a time trial said so; the member's own bib, category, laps and start
      const [before, after] = t('mp.raceOf', { title: '\u0000' }).split('\u0000'), a = document.createElement('a');
      a.href = langPath(g.event.url); a.target = '_top'; a.textContent = L(g.event.title);
      small.append(before, a, after + (g.mode === 'itt' ? t('mp.raceItt') : '') + (g.me ? t('mp.raceMe', { bib: g.me.bib, group: g.me.group, laps: g.me.laps }) + (g.me.start_offset_s ? t('mp.raceStart', { t: fmtTime(g.me.start_offset_s) }) : '') : ''));
    } else if (g.mode === 'itt') { // a time trial without an event: the member's own start, as they joined
      small.append(t('mp.raceItt') + (g.me && g.me.start_offset_s ? t('mp.raceStart', { t: fmtTime(g.me.start_offset_s) }) : ''));
    }
    const share = card.querySelector('.share'); share.textContent = t('mp.share'); share.onclick = () => mpShare(g);
    const btn = card.querySelector('.act'); btn.disabled = false;
    if (g.is_host) { btn.textContent = t('mp.cancel'); btn.onclick = () => mpAction('/groups/' + g.id + '/cancel'); }
    else if (g.is_member) { btn.textContent = t('mp.leave'); btn.onclick = () => mpAction('/groups/' + g.id + '/leave'); }
    else { btn.textContent = t('mp.join'); btn.disabled = mpClash(g) || left === 0; btn.onclick = () => mpAction('/groups/' + g.id + '/join'); }
  });
  // one race to wait for at a time; one at a date and time keeps an hour from the others, as the site checks
  create.disabled = !mpKind() || !!MP.eventBusy || (!!mine && $('#mpDelay').value !== 'at');
  renderStartSum();
}
// in a race with protocols the rider's own category: its riders ride its laps, the others are not in the same race
function sameCategory() {
  const mine = groupRide && groupRide.race && groupRide.race.me ? groupRide.race.me.group : null;
  return group => mine == null || (group || '') === mine;
}
function raceList() {
  const same = sameCategory();
  const list = [{ name: t('you'), t: me.finishT, me: true, color: hexs(kitted(charById(settings.char)).a) }].concat(bots.filter(b => same(b.group)).map(b => ({ name: b.name, t: b.finishT != null ? b.finishT : raceT + (world.FIN - b.s) / Math.max(b.v, 2), color: hexs(b.color), est: b.finishT == null, human: !!b.remote })));
  list.sort((a, b) => a.t - b.t); return list;
}
function renderRaceList(list) {
  $('#resList').innerHTML = list.map((x, i) => '<li class="' + (x.me ? 'me' : '') + '"><span>' + (i + 1) + '</span><span><span style="display:inline-block;width:9px;height:9px;border-radius:50%;background:' + x.color + ';margin-right:8px"></span>' + escapeHTML(x.name) + (x.human ? ' <small style="color:var(--muted)">' + t('res.human') + '</small>' : '') + '</span><span>' + (x.est ? (x.human ? t('res.onTheWay') : '≈ ') : '') + fmtTime(x.t) + '</span></li>').join('');
}
function escapeHTML(t) { return String(t).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]); }
setInterval(() => { if (phase === 'menu' && MP.status === 'on') { mpMaybeStart(); renderMP(); } }, 1000);
