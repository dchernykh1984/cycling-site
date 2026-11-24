'use strict';
/* ---------------- Устройства Bluetooth: датчики CSC, пульсометры, измерители мощности, умные станки FTMS ---------------- */
const UUID = { csc: 0x1816, hr: 0x180D, cp: 0x1818, ftms: 0x1826, cscMeas: 0x2A5B, cscFeat: 0x2A5C, hrMeas: 0x2A37, cpMeas: 0x2A63, ibd: 0x2AD2, ftmsCP: 0x2AD9, ftmsFeat: 0x2ACC, powerRange: 0x2AD8 };
const fits = (dv, o, n) => o + n <= dv.byteLength;
const CONTROL_ANSWER_MS = 2000; // how long a trainer may take to answer a command
function parseCSC(dv) {
  let o = 0; const f = dv.getUint8(o); o += 1; const r = {};
  if ((f & 1) && fits(dv, o, 6)) { r.wr = dv.getUint32(o, true); r.wt = dv.getUint16(o + 4, true); o += 6; }
  if ((f & 2) && fits(dv, o, 4)) { r.cr = dv.getUint16(o, true); r.ct = dv.getUint16(o + 2, true); o += 4; }
  return r;
}
function parseHR(dv) { const f = dv.getUint8(0); return (f & 1) ? dv.getUint16(1, true) : dv.getUint8(1); }
// FTMS Indoor Bike Data (0x2AD2)
function parseIBD(dv) {
  let o = 0; const f = dv.getUint16(o, true); o += 2; const r = {};
  if (!(f & 1)) { if (fits(dv, o, 2)) r.speed = dv.getUint16(o, true) / 100; o += 2; }
  if (f & 2) o += 2;
  if (f & 4) { if (fits(dv, o, 2)) r.cad = dv.getUint16(o, true) / 2; o += 2; }
  if (f & 8) o += 2;
  if (f & 16) o += 3;
  if (f & 32) o += 2;
  if (f & 64) { if (fits(dv, o, 2)) r.power = dv.getInt16(o, true); o += 2; }
  if (f & 128) o += 2;
  if (f & 256) o += 5;
  if (f & 512) { if (fits(dv, o, 1)) r.hr = dv.getUint8(o); o += 1; }
  return r;
}
// Cycling Power Measurement (0x2A63)
function parseCP(dv) {
  let o = 0; const f = dv.getUint16(o, true); o += 2; const r = { power: dv.getInt16(o, true) }; o += 2;
  if (f & 1) o += 1; if (f & 4) o += 2;
  if (f & 16) o += 6;
  if ((f & 32) && fits(dv, o, 4)) { r.cr = dv.getUint16(o, true); r.ct = dv.getUint16(o + 2, true); }
  return r;
}
const ROLE_NAMES = [['speed', t('role.speed')], ['cadence', t('role.cadence')], ['power', t('role.power')], ['hr', t('role.hr')], ['trainer', t('role.trainer')]];
class BLEDev {
  constructor(dev) {
    this.dev = dev; this.name = dev.name || t('dev.unnamed'); this.roles = new Set(); this.status = 'connecting'; this.retries = 0; this.ls = new WeakSet();
    this.wheelRpm = 0; this.crankRpm = 0; this.hrV = 0; this.powerV = 0; this.at = { w: 0, c: 0, h: 0, p: 0 };
    this.pw = null; this.pc = null; this.ctrl = false; this.busy = false; this.hasFtms = false; this.ergRange = null;
  }
  role(r) { if (!this.roles.has(r)) { this.roles.add(r); Sensors.changed(); } }
  async svc(server, u) { try { return await server.getPrimaryService(u); } catch (e) { return null; } }
  async sub(svc, uuid, fn) {
    const ch = await svc.getCharacteristic(uuid);
    if (!this.ls.has(ch)) { this.ls.add(ch); ch.addEventListener('characteristicvaluechanged', e => { try { fn(e.target.value); } catch (err) {} }); }
    await ch.startNotifications(); return ch;
  }
  async connect() {
    this.link = (this.link || 0) + 1; // each connection is told apart, so an answer from the last one is not taken for this one's
    const server = await this.dev.gatt.connect();
    const ftms = await this.svc(server, UUID.ftms), cp = await this.svc(server, UUID.cp), csc = await this.svc(server, UUID.csc), hr = await this.svc(server, UUID.hr);
    if (ftms) {
      this.hasFtms = true;
      try { await this.sub(ftms, UUID.ibd, dv => this.onIBD(dv)); this.roles.add('trainer'); this.roles.add('power'); } catch (e) {}
      await this.readTargets(ftms);
      try {
        this.cpt = await ftms.getCharacteristic(UUID.ftmsCP);
        if (!this.ls.has(this.cpt)) { this.ls.add(this.cpt); this.cpt.addEventListener('characteristicvaluechanged', e => this.onCtrl(e.target.value)); }
        await this.cpt.startNotifications();
        this.ctrl = await this.takeControl();
      } catch (e) { this.ctrl = false; }
    }
    if (cp && !ftms) { try { await this.sub(cp, UUID.cpMeas, dv => this.onCP(dv)); this.roles.add('power'); } catch (e) {} }
    if (csc) {
      try { const f = await csc.getCharacteristic(UUID.cscFeat); const b = (await f.readValue()).getUint16(0, true); if (b & 1) this.roles.add('speed'); if (b & 2) this.roles.add('cadence'); } catch (e) {}
      try { await this.sub(csc, UUID.cscMeas, dv => this.onCSC(dv)); } catch (e) {}
    }
    if (hr) { try { await this.sub(hr, UUID.hrMeas, dv => { this.hrV = parseHR(dv); this.at.h = performance.now(); }); this.roles.add('hr'); } catch (e) {} }
    if (!ftms && !cp && !csc && !hr) throw new Error('no supported services');
    if (!this._d) { this._d = () => this.onDisc(); this.dev.addEventListener('gattserverdisconnected', this._d); }
    this.status = 'online'; this.retries = 0; Sensors.changed();
  }
  // Whether the trainer holds a power itself (ERG): the second field of its Fitness Machine Feature (0x2ACC)
  // has bit 3, Power Target Setting, and then it reports the watts it can hold (Supported Power Range, 0x2AD8)
  async readTargets(ftms) {
    this.ergRange = null;
    try {
      const f = await (await ftms.getCharacteristic(UUID.ftmsFeat)).readValue();
      if (f.byteLength < 8 || !(f.getUint32(4, true) & 8)) return;
      this.ergRange = [0, 2000];
      const r = await (await ftms.getCharacteristic(UUID.powerRange)).readValue();
      if (r.byteLength >= 4 && r.getInt16(2, true) > r.getInt16(0, true)) this.ergRange = [Math.max(0, r.getInt16(0, true)), r.getInt16(2, true)];
    } catch (e) {}
  }
  async write(bytes) { const data = new Uint8Array(bytes); if (this.cpt.writeValueWithResponse) await this.cpt.writeValueWithResponse(data); else await this.cpt.writeValue(data); }
  // A command to the FTMS control point is answered by an indication [0x80, opcode, result]; until it is,
  // the trainer refuses the next command (Procedure Already In Progress), so each command waits for its
  // answer. Resolves to the result (1 = success, 5 = control not permitted, ...), null when no answer came
  // in time (some trainers never answer), -1 when the write itself failed.
  command(bytes) {
    return new Promise(resolve => {
      const done = r => { clearTimeout(timer); if (this.pending === wait) this.pending = null; resolve(r); };
      const wait = { op: bytes[0], done }, timer = setTimeout(() => done(null), CONTROL_ANSWER_MS);
      this.pending = wait;
      this.write(bytes).catch(e => { console.warn('[trainer] command ' + bytes[0] + ' failed: ' + e.message); done(-1); });
    });
  }
  onCtrl(dv) {
    if (dv.byteLength < 3 || dv.getUint8(0) !== 0x80) return;
    if (this.pending && this.pending.op === dv.getUint8(1)) this.pending.done(dv.getUint8(2));
  }
  // request control, then start; a trainer that never answers is tried all the same, as before
  async takeControl() {
    const r = await this.command([0x00]);
    if (r !== 1 && r !== null) { if (r > 1) toast(t('dev.noControl')); return false; }
    await this.command([0x07]);
    return true;
  }
  // one setting for the trainer, as its controller: true once it took it (or never answers, as some do)
  async control(cmd) {
    this.answer = undefined; // what the trainer answered this command, for the caller to read
    if (!this.ctrl || this.busy) return false; this.busy = true;
    const link = this.link;
    try {
      let r = await this.command(cmd);
      if (r === 5) { // the trainer let go of control (a reset, another app): ask once more, and if it says no, stop asking
        if (await this.takeControl()) r = await this.command(cmd);
        else { this.ctrl = false; Sensors.changed(); return false; }
      }
      this.answer = r;
      return link === this.link && (r === 1 || r === null);
    } finally { this.busy = false; }
  }
  setGrade(g, drag) {
    const v = Math.round(clamp(g, -10, 20) * 100);
    return this.control([0x11, 0, 0, v & 255, (v >> 8) & 255, Math.round(drag.crr * 1e4), Math.round(drag.cw * 100)]); // FTMS: wind speed 0, grade in 0.01 %, Crr in 0.0001, Cw in 0.01 kg/m
  }
  // ERG: the trainer holds the power whatever the cadence (FTMS Set Target Power, watts within its range). One
  // that said it can and still refuses the command (Op Code Not Supported, Invalid Parameter) is ridden by the
  // grade from then on, rather than told the power every second and moved by nothing
  async setPower(w) {
    const v = Math.round(clamp(w, this.ergRange[0], this.ergRange[1])), ok = await this.control([0x05, v & 255, (v >> 8) & 255]);
    if (!ok && (this.answer === 2 || this.answer === 3)) { this.ergRange = null; Sensors.changed(); }
    return ok;
  }
  onIBD(dv) {
    const r = parseIBD(dv), now = performance.now();
    if (r.power != null) { this.powerV = Math.max(0, r.power); this.at.p = now; }
    if (r.cad != null) { this.crankRpm = r.cad; this.at.c = now; this.role('cadence'); }
    if (r.hr) { this.hrV = r.hr; this.at.h = now; this.role('hr'); }
  }
  onCP(dv) {
    const r = parseCP(dv), now = performance.now();
    this.powerV = Math.max(0, r.power); this.at.p = now;
    if (r.cr != null) { this.role('cadence'); this.crankFrom(r.cr, r.ct, now); }
  }
  crankFrom(cr, ct, now) {
    if (this.pc) { const dr = (cr - this.pc.r + 65536) % 65536, dt = ((ct - this.pc.t + 65536) % 65536) / 1024; if (dr > 0 && dr < 50 && dt > 0) { const rpm = clamp(dr / dt * 60, 0, 220); this.crankRpm = this.crankRpm ? lerp(this.crankRpm, rpm, .5) : rpm; this.at.c = now; } }
    this.pc = { r: cr, t: ct };
  }
  onCSC(dv) {
    const now = performance.now(), m = parseCSC(dv);
    if (m.wr != null) {
      this.role('speed');
      if (this.pw) { const dr = (m.wr - this.pw.r) >>> 0, dt = ((m.wt - this.pw.t + 65536) % 65536) / 1024; if (dr > 0 && dr < 500 && dt > 0) { const rpm = dr / dt * 60; this.wheelRpm = this.wheelRpm ? lerp(this.wheelRpm, rpm, .5) : rpm; this.at.w = now; } }
      this.pw = { r: m.wr, t: m.wt };
    }
    if (m.cr != null) { this.role('cadence'); this.crankFrom(m.cr, m.ct, now); }
  }
  tick(now) {
    if (now - this.at.w > 2500) this.wheelRpm = 0;
    if (now - this.at.c > 3000) this.crankRpm = 0;
    if (now - this.at.h > 5000) this.hrV = 0;
    if (now - this.at.p > 3000) this.powerV = 0;
  }
  // Датчики засыпают и рвут связь, когда педали стоят. Переподключаемся без ограничения попыток,
  // пока пользователь сам не отключит устройство.
  async onDisc() {
    this.ctrl = false; this.wheelRpm = this.crankRpm = this.hrV = this.powerV = 0; this.pw = this.pc = null;
    if (this.manual || this.reconnecting) return;
    this.reconnecting = true; this.status = 'reconnecting'; Sensors.changed();
    if (phase === 'race') toast(t('dev.lost', { name: this.name }), 3.5);
    while (!this.manual) {
      await new Promise(r => setTimeout(r, Math.min(1000 + this.retries * 1000, 5000)));
      if (this.manual) break;
      this.retries++;
      try { await this.connect(); this.pw = this.pc = null; Trainer.sent = Trainer.held = null; toast(t('dev.back', { name: this.name })); break; } catch (e) {}
    }
    this.reconnecting = false;
  }
  disconnect() { this.manual = true; try { this.dev.gatt.disconnect(); } catch (e) {} }
}
const SERVICES = [UUID.ftms, UUID.cp, UUID.csc, UUID.hr];
const ANY_SENSOR = { filters: SERVICES.map(u => ({ services: [u] })), optionalServices: SERVICES };
// Devices once connected are remembered by the id the browser gives them for this site and by their name.
// A page opens a remembered device without the chooser only where the browser lists the devices the site was
// given (navigator.bluetooth.getDevices) -- Chrome behind chrome://flags/#enable-web-bluetooth-new-permissions-backend;
// elsewhere Connect opens the chooser with that device alone in it.
const Sensors = {
  devs: [],
  saved: [], auto: false,
  // what the page remembered: read as the page starts, the browser's storage being the page's (js/helpers.js)
  restore() {
    const kept = store.get('devices', []);
    this.saved = (Array.isArray(kept) ? kept : []).filter(s => s && typeof s.id === 'string').slice(0, 8);
    this.auto = store.get('btAuto', false) === true;
  },
  supported() { return !!(navigator.bluetooth && navigator.bluetooth.requestDevice); },
  canReopen() { return !!(navigator.bluetooth && navigator.bluetooth.getDevices); },
  async add() {
    if (!this.supported()) { btHint(isIOS() ? t('bt.iosAdd') : t('bt.noneAdd'), true); return; }
    await this.pick(ANY_SENSOR);
  },
  async pick(options) {
    let dev;
    try { dev = await navigator.bluetooth.requestDevice(options); } catch (e) {
      if (e.name === 'NotFoundError') return; // окно выбора закрыто
      btHint(e.name === 'SecurityError' ? t('bt.blocked') : t('bt.pickFailed', { msg: e.message }), true); return;
    }
    await this.open(dev);
  },
  // quiet: opened with the page, so a device still asleep is tried again until it wakes, not given up on
  async open(dev, quiet) {
    if (this.devs.some(d => d.dev.id === dev.id)) { if (!quiet) btHint(t('bt.already')); return; }
    const d = new BLEDev(dev); this.devs.push(d); this.changed();
    try {
      await d.connect(); this.remember(d);
      btHint(d.roles.has('trainer') ? (d.ctrl ? t('bt.trainerCtrl') : t('bt.trainerNoCtrl')) : d.roles.has('hr') && d.roles.size === 1 ? t('bt.hrOk') : t('bt.connected', { name: d.name }));
    } catch (e) {
      if (quiet) { d.onDisc(); return; }
      this.devs = this.devs.filter(x => x !== d); this.changed(); btHint(t('bt.failed'), true);
    }
  },
  // the newest first; one entry a device, matched by its id or, where the browser gave it a new id, its name
  remember(d) {
    const name = d.dev.name || '';
    this.saved = [{ id: d.dev.id, name }, ...this.saved.filter(s => s.id !== d.dev.id && !(name && s.name === name))].slice(0, 8);
    store.set('devices', this.saved); this.changed();
  },
  async permitted(entry) {
    if (!this.canReopen()) return null;
    try { return (await navigator.bluetooth.getDevices()).find(x => x.id === entry.id) || null; } catch (e) { return null; }
  },
  async reopen(entry) {
    if (!this.supported()) { btHint(isIOS() ? t('bt.iosAdd') : t('bt.noneAdd'), true); return; }
    const dev = await this.permitted(entry);
    if (dev) await this.open(dev);
    else await this.pick(entry.name ? { filters: [{ name: entry.name }], optionalServices: SERVICES } : ANY_SENSOR);
  },
  forget(entry) {
    this.saved = this.saved.filter(s => s.id !== entry.id); store.set('devices', this.saved); this.changed();
    this.permitted(entry).then(dev => { if (dev && dev.forget) dev.forget().catch(() => {}); });
  },
  setAuto(on) {
    this.auto = on; store.set('btAuto', on);
    if (on && this.supported() && !this.canReopen()) btHint(t('bt.autoBlocked'), true); else if (on) this.autoConnect();
  },
  // with the page: every remembered device the browser still lets the site open, each one tried until it wakes
  async autoConnect() {
    if (!this.auto || !this.saved.length || !this.supported()) return;
    if (!this.canReopen()) { btHint(t('bt.autoBlocked'), true); return; }
    for (const entry of this.saved) {
      const dev = await this.permitted(entry);
      if (!dev) continue;
      if (dev.watchAdvertisements) dev.watchAdvertisements().catch(() => {}); // so the browser looks for it while it sleeps
      this.open(dev, true);
    }
  },
  remove(d) { d.disconnect(); this.devs = this.devs.filter(x => x !== d); this.changed(); },
  tick(now) { this.devs.forEach(d => d.tick(now)); },
  // устройство, которое переподключается, остаётся источником данных (с нулями), чтобы заезд не переключался в демо-режим
  live(role) { return this.devs.filter(d => d.roles.has(role)); },
  trainer() { return this.live('trainer')[0] || null; },
  power() { const d = this.live('trainer')[0] || this.live('power')[0]; return d ? d.powerV : null; },
  wheel() { const d = this.live('speed')[0]; return d ? d.wheelRpm : null; },
  crank() { const l = this.live('cadence'); if (!l.length) return null; const fresh = l.find(d => d.crankRpm > 0); return (fresh || l[0]).crankRpm; },
  hr() { const d = this.live('hr').find(d => d.hrV > 0); return d ? d.hrV : null; },
  mode() { if (this.power() != null) return 'power'; if (this.wheel() != null) return 'speed'; if (this.crank() != null) return 'cadence'; return 'demo'; },
  changed() { renderDevs(); updateModeUI(); }
};
// Управление сопротивлением: шлём уклон маршрута не чаще раза в секунду и только при изменении (и раз в 5 с без него);
// сопротивление самого гонщика уходит вместе с каждым уклоном. Power to hold (watts, a workout's step with ERG
// on) goes instead of the grade on a trainer that holds it: sent (the grade) and held (the power) say which is on it.
// A change of the rider's wind resistance (a wake ahead, the air higher up) is sent as a change of the grade is;
// cw is the last one sent, in the 0.01 kg/m the trainer reads
const Trainer = {
  last: -10, sent: null, held: null, cw: null,
  update(t, grade, rider, watts) {
    const d = Sensors.trainer(); if (!d || !d.ctrl) return;
    if (t - this.last < 1) return;
    if (watts != null && d.ergRange) {
      if (this.held !== null && Math.abs(watts - this.held) < 1 && t - this.last < 5) return;
      this.last = t; this.sent = null; d.setPower(watts).then(ok => { if (ok) this.held = watts; }); return;
    }
    const target = trainerGrade(grade, settings.difficulty), drag = trainerDrag(rider), cw = Math.round(drag.cw * 100);
    if (this.held === null && this.sent !== null && Math.abs(target - this.sent) < .2 && cw === this.cw && t - this.last < 5) return;
    this.last = t; d.setGrade(target, drag).then(ok => { if (ok) { this.sent = target; this.cw = cw; this.held = null; } });
  },
  info() { const d = Sensors.trainer(); return d && d.ctrl && this.sent != null ? this.sent : null; },
  canErg() { const d = Sensors.trainer(); return !!(d && d.ctrl && d.ergRange); }
};
function isIOS() { return /iP(hone|ad|od)/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1); }
function btHint(t, warn) { const h = $('#btHint'); h.textContent = t; h.classList.toggle('warn', !!warn); }
function renderDevs() {
  const ul = $('#devList'); ul.innerHTML = '';
  Sensors.devs.forEach(d => {
    const li = document.createElement('li'); li.className = 'dev';
    const tags = ROLE_NAMES.filter(r => d.roles.has(r[0])).map(r => '<span class="tag on">' + r[1] + '</span>').join('') + (d.ergRange ? '<span class="tag on">ERG</span>' : '') + (d.roles.has('trainer') && !d.ctrl && d.status === 'online' ? '<span class="tag">' + t('dev.noCtrlTag') + '</span>' : '') || '<span class="tag">' + t('dev.detecting') + '</span>';
    li.innerHTML = '<div><b></b><br><small></small><div class="tags">' + tags + '</div></div>';
    li.querySelector('b').textContent = d.name; li.querySelector('small').textContent = d.status === 'online' ? t('dev.online') : d.status === 'reconnecting' ? t('dev.reconnecting') : t('dev.connecting');
    const btn = document.createElement('button'); btn.className = 'btn'; btn.type = 'button'; btn.textContent = t('dev.disconnect'); btn.onclick = () => Sensors.remove(d);
    li.appendChild(btn); ul.appendChild(li);
  });
  // remembered devices not connected now: one press connects one, Forget drops it
  Sensors.saved.filter(s => !Sensors.devs.some(d => d.dev.id === s.id)).forEach(s => {
    const li = document.createElement('li'); li.className = 'dev saved';
    li.innerHTML = '<div><b></b><br><small></small></div><div class="devBtns"></div>';
    li.querySelector('b').textContent = s.name || t('dev.unnamed'); li.querySelector('small').textContent = t('dev.notConnected');
    [[t('dev.connectSaved'), () => Sensors.reopen(s)], [t('dev.forget'), () => Sensors.forget(s)]].forEach(([label, act]) => {
      const btn = document.createElement('button'); btn.className = 'btn'; btn.type = 'button'; btn.textContent = label; btn.onclick = act;
      li.querySelector('.devBtns').appendChild(btn);
    });
    ul.appendChild(li);
  });
  const auto = $('#btAuto'); if (auto) auto.checked = Sensors.auto;
}
