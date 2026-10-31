'use strict';
const MP = { status: 'connecting', online: [], groups: [], riders: [], offset: 0, busy: false, timer: null, started: new Set(), lastInp: null, resultsFor: null, linkShown: false, linkChecked: false };
// a group race named by the link the page was opened with (?group=)
const LINKED = (g => /^[0-9]{1,12}$/.test(g || '') ? +g : null)(new URLSearchParams(location.search).get('group'));
// the address of a group race: the site's page that frames the trainer, which also hands a newcomer
// the cookie the page needs to join -- never this file on its own
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
    if (navigator.share) { await navigator.share({ title: t('mp.shareTitle', { route: routeTitle(g) }), url }); return; }
    await navigator.clipboard.writeText(url); mpNote(t('mp.copied', { url }));
  } catch (e) { if (e.name !== 'AbortError') mpNote(t('mp.copyFailed', { url })); }
}
// a linked race that is not open any more says why, once
async function mpCheckLink() {
  if (!LINKED || MP.linkChecked || MP.groups.some(g => g.id === LINKED)) return;
  MP.linkChecked = true;
  try { const g = await Site.get('/groups/' + LINKED); mpNote(g.cancelled ? t('mp.linkCancelled') : t('mp.linkStarted')); }
  catch (e) { if (e.status === 404) mpNote(t('mp.linkMissing')); }
}
let groupRide = null;   // { gid, startAt } во время групповой гонки
let rideMode = 'race';  // режим текущего заезда: race | plan | free
const MP_COLORS = [0x2f6db5, 0x3f8f5a, 0x7a4fb0, 0x1f9aa3, 0xb53f7a, 0xe5a23a, 0x5a6470, 0xd36b2c, 0x2c3e8f, 0x8fa33a];
const mpColor = id => MP_COLORS[Math.abs(+id || 0) % MP_COLORS.length];
const mpStartLocal = g => Date.parse(g.start_at) - MP.offset;   // время старта по своим часам
function mpInit() {
  if (!Records.synced) { MP.status = Records.me ? 'guest' : 'off'; renderMP(); return; }
  MP.status = 'on'; mpPoll();
}
function mpSchedule(ms) { clearTimeout(MP.timer); MP.timer = setTimeout(mpPoll, ms); }
async function mpPoll() {
  if (MP.status !== 'on') return;
  if (MP.busy) { mpSchedule(300); return; }
  MP.busy = true;
  const riding = phase !== 'menu' && world && me, inp = MP.lastInp || {};
  const body = riding
    ? { status: 'ride', route: world.route.id, mode: rideMode, group_id: groupRide ? groupRide.gid : null, distance_m: Math.round(me.s * 10) / 10, speed_ms: Math.round(me.v * 100) / 100, cadence_rpm: Math.round(clamp(inp.cad || 0, 0, 250)), power_w: Math.round(clamp(inp.P || 0, 0, 3000)), lane_m: Math.round(me.lane * 10) / 10, finished_s: me.finishT != null ? Math.round(me.finishT * 10) / 10 : null }
    : { status: 'lobby', route: routeSel };
  const t0 = Date.now();
  try {
    const res = await Site.post('/presence', body), t1 = Date.now();
    MP.offset = Date.parse(res.server_now) - (t0 + t1) / 2;
    MP.online = res.online || []; MP.riders = res.riders || []; MP.recv = t1;
    if (!riding) MP.groups = res.groups || [];
    if (phase === 'menu') { mpMaybeStart(); renderMP(); mpCheckLink(); } else mpSyncRemotes();
  } catch (e) {
    if (e.status === 401 || e.status === 403) { MP.status = 'guest'; renderMP(); MP.busy = false; return; }
  }
  MP.busy = false;
  mpSchedule(phase === 'menu' ? 3000 : 1000);
}
function mpMyGroup() { return MP.groups.find(g => g.is_member); }
function mpMaybeStart() {
  const g = mpMyGroup(); if (!g || MP.started.has(g.id)) return;
  const at = mpStartLocal(g), now = Date.now();
  if (now >= at - 7000 && now < at + 30000) { MP.started.add(g.id); groupRide = { gid: g.id, startAt: at }; routeSel = g.route; renderMenu(); startRace(); }
}
async function mpAction(path, body) {
  try { await Site.post(path, body); } catch (e) { $('#mpStatus').textContent = t('mp.failed', { msg: e.message }); }
  mpSchedule(50);
}
function mpCreateGroup() {
  if (MP.status !== 'on' || mpMyGroup()) return;
  const r = ROUTES.find(x => x.id === routeSel) || ROUTES[0];
  mpAction('/groups', { route: r.id, route_name: r.name, start_in_s: +$('#mpDelay').value || 60 });
}
// "Start" while waiting: the rider rides alone and the race goes on without them (a host hands it on)
async function mpLeaveMyGroup() { const g = mpMyGroup(); if (g) await mpAction('/groups/' + g.id + '/leave'); }

// живые соперники: те же записи, что у ботов, но без своей физики
function mpSyncRemotes() {
  if (!world || phase === 'menu') return;
  const want = new Map(MP.riders.filter(r => r.route === world.route.id).map(r => [r.user_id, r]));
  // кто пропал из ответа, остаётся на трассе ещё 20 с: связь у соседа могла просто запнуться
  const nowMs = performance.now();
  for (let i = bots.length - 1; i >= 0; i--) { const b = bots[i]; if (b.remote && !want.has(b.uid) && nowMs - (b.seenAt || 0) > 20000) { scene.remove(b.mesh.g); bots.splice(i, 1); } }
  let changedFinish = false;
  want.forEach((r, uid) => {
    let b = bots.find(x => x.remote && x.uid === uid);
    if (!b) {
      const col = mpColor(uid), ch = Object.assign({}, kitted(PLAYER_CH), { helmet: col, stripe: col });
      b = newRider(r.name || t('mp.rider'), col, 75, r.distance_m, clamp(r.lane_m || 2, .5, world.route.width / 2 - .8));
      Object.assign(b, { remote: true, uid, ch, mesh: makeRider(ch), seed: 0, wkg: 0 });
      scene.add(b.mesh.g); bots.push(b);
    }
    b.seenAt = nowMs; b.sampleS = r.distance_m; b.sampleT = performance.now() - (r.age_s || 0) * 1000; b.v = r.speed_ms || 0; b.cad = r.cadence_rpm || 0; b.P = r.power_w || 0;
    b.lane = clamp(r.lane_m || b.lane, .5, world.route.width / 2 - .8); b.name = r.name || t('mp.rider');
    const f = typeof r.finished_s === 'number' ? r.finished_s : null; if (f !== b.finishT) { b.finishT = f; changedFinish = true; }
  });
  if (changedFinish && phase === 'done' && rideMode === 'race' && me.finishT != null && !MP.resultsFor) renderRaceList(raceList());
}
function mpStepRemote(b, dt) {
  const pred = b.sampleS + b.v * Math.min(2.5, (performance.now() - b.sampleT) / 1000);
  if (Math.abs(pred - b.s) > 60) b.s = pred; else b.s += (pred - b.s) * (1 - Math.exp(-dt * 4));
  b.phase += (b.cad || 0) / 60 * Math.PI * 2 * dt;
}
// итоги групповой гонки с сервера: время тех, кто финишировал, и тех, кто ещё едет
async function mpPollResults(gid, until) {
  if (phase !== 'done' || !groupRide || groupRide.gid !== gid || Date.now() > until) { MP.resultsFor = null; return; }
  MP.resultsFor = gid;
  try {
    const res = await Site.get('/groups/' + gid + '/results'), myId = Records.me && Records.me.user_id;
    const done = new Set(res.finished.map(f => f.user_id));
    const list = res.finished.map(f => ({ name: f.user_id === myId ? t('you') : f.name, t: f.duration_s, me: f.user_id === myId, color: f.user_id === myId ? hexs(kitted(charById(settings.char)).a) : hexs(mpColor(f.user_id)), human: f.user_id !== myId }));
    if (!done.has(myId) && me.finishT != null) list.push({ name: t('you'), t: me.finishT, me: true, color: hexs(kitted(charById(settings.char)).a) });
    bots.filter(b => b.remote && !done.has(b.uid)).forEach(b => list.push({ name: b.name, t: raceT + (world.FIN - b.s) / Math.max(b.v, 2), color: hexs(b.color), est: true, human: true }));
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
    const left = Math.max(0, Math.ceil((mpStartLocal(g) - Date.now()) / 1000));
    let card = box.querySelector('[data-gid="' + g.id + '"]');
    if (!card) {
      card = document.createElement('div'); card.dataset.gid = g.id;
      card.innerHTML = '<div><b></b><small></small></div><div class="mp-acts"><button class="btn act" type="button"></button><button class="btn share" type="button"></button></div>';
      box.appendChild(card);
    }
    card.className = 'mp-group' + (g.is_member ? ' on' : '') + (g.id === LINKED ? ' linked' : '');
    if (g.id === LINKED && !MP.linkShown) { MP.linkShown = true; card.scrollIntoView({ block: 'center' }); } // what the link named
    card.querySelector('b').textContent = (g.is_host ? t('mp.yours') : t('mp.hostGathers', { name: g.host.name })) + ': ' + routeTitle(g);
    card.querySelector('small').textContent = (g.id === LINKED ? t('mp.byLink') : '') + (left ? t('mp.startsIn', { t: fmtTime(left) }) : t('mp.starting')) + t('mp.members', { list: g.members.map(m => (Records.me && m.user_id === Records.me.user_id) ? t('youLower') : m.name).join(', ') });
    const share = card.querySelector('.share'); share.textContent = t('mp.share'); share.onclick = () => mpShare(g);
    const btn = card.querySelector('.act'); btn.disabled = false;
    if (g.is_host) { btn.textContent = t('mp.cancel'); btn.onclick = () => mpAction('/groups/' + g.id + '/cancel'); }
    else if (g.is_member) { btn.textContent = t('mp.leave'); btn.onclick = () => mpAction('/groups/' + g.id + '/leave'); }
    else { btn.textContent = t('mp.join'); btn.disabled = !!mine || left === 0; btn.onclick = () => mpAction('/groups/' + g.id + '/join'); }
  });
  create.disabled = !!mine;
  renderStartSum();
}
function raceList() {
  const list = [{ name: t('you'), t: me.finishT, me: true, color: hexs(kitted(charById(settings.char)).a) }].concat(bots.map(b => ({ name: b.name, t: b.finishT != null ? b.finishT : raceT + (world.FIN - b.s) / Math.max(b.v, 2), color: hexs(b.color), est: b.finishT == null, human: !!b.remote })));
  list.sort((a, b) => a.t - b.t); return list;
}
function renderRaceList(list) {
  $('#resList').innerHTML = list.map((x, i) => '<li class="' + (x.me ? 'me' : '') + '"><span>' + (i + 1) + '</span><span><span style="display:inline-block;width:9px;height:9px;border-radius:50%;background:' + x.color + ';margin-right:8px"></span>' + escapeHTML(x.name) + (x.human ? ' <small style="color:var(--muted)">' + t('res.human') + '</small>' : '') + '</span><span>' + (x.est ? (x.human ? t('res.onTheWay') : '≈ ') : '') + fmtTime(x.t) + '</span></li>').join('');
}
function escapeHTML(t) { return String(t).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]); }
setInterval(() => { if (phase === 'menu' && MP.status === 'on') { mpMaybeStart(); renderMP(); } }, 1000);
