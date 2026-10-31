'use strict';
/* ---------------- Устройства Bluetooth: датчики CSC, пульсометры, измерители мощности, умные станки FTMS ---------------- */
const UUID = { csc: 0x1816, hr: 0x180D, cp: 0x1818, ftms: 0x1826, cscMeas: 0x2A5B, cscFeat: 0x2A5C, hrMeas: 0x2A37, cpMeas: 0x2A63, ibd: 0x2AD2, ftmsCP: 0x2AD9 };
const fits = (dv, o, n) => o + n <= dv.byteLength;
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
    this.pw = null; this.pc = null; this.ctrl = false; this.busy = false; this.hasFtms = false;
  }
  role(r) { if (!this.roles.has(r)) { this.roles.add(r); Sensors.changed(); } }
  async svc(server, u) { try { return await server.getPrimaryService(u); } catch (e) { return null; } }
  async sub(svc, uuid, fn) {
    const ch = await svc.getCharacteristic(uuid);
    if (!this.ls.has(ch)) { this.ls.add(ch); ch.addEventListener('characteristicvaluechanged', e => { try { fn(e.target.value); } catch (err) {} }); }
    await ch.startNotifications(); return ch;
  }
  async connect() {
    const server = await this.dev.gatt.connect();
    const ftms = await this.svc(server, UUID.ftms), cp = await this.svc(server, UUID.cp), csc = await this.svc(server, UUID.csc), hr = await this.svc(server, UUID.hr);
    if (ftms) {
      this.hasFtms = true;
      try { await this.sub(ftms, UUID.ibd, dv => this.onIBD(dv)); this.roles.add('trainer'); this.roles.add('power'); } catch (e) {}
      try {
        this.cpt = await ftms.getCharacteristic(UUID.ftmsCP);
        if (!this.ls.has(this.cpt)) { this.ls.add(this.cpt); this.cpt.addEventListener('characteristicvaluechanged', e => this.onCtrl(e.target.value)); }
        await this.cpt.startNotifications();
        await this.write([0x00]); // запросить управление
        await this.write([0x07]); // старт
        this.ctrl = true;
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
  async write(bytes) { const data = new Uint8Array(bytes); if (this.cpt.writeValueWithResponse) await this.cpt.writeValueWithResponse(data); else await this.cpt.writeValue(data); }
  onCtrl(dv) { if (dv.getUint8(0) === 0x80 && dv.byteLength >= 3 && dv.getUint8(1) === 0x00 && dv.getUint8(2) !== 1) { this.ctrl = false; Sensors.changed(); toast(t('dev.noControl')); } }
  async setGrade(g) {
    if (!this.ctrl || this.busy) return false; this.busy = true;
    try { const v = Math.round(clamp(g, -10, 20) * 100); await this.write([0x11, 0, 0, v & 255, (v >> 8) & 255, 40, 51]); return true; } // ветер 0, уклон 0,01 %, Crr 0,004, CdA·ρ/2 ≈ 0,51
    catch (e) { return false; } finally { this.busy = false; }
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
      try { await this.connect(); this.pw = this.pc = null; Trainer.sent = null; toast(t('dev.back', { name: this.name })); break; } catch (e) {}
    }
    this.reconnecting = false;
  }
  disconnect() { this.manual = true; try { this.dev.gatt.disconnect(); } catch (e) {} }
}
const Sensors = {
  devs: [],
  supported() { return !!(navigator.bluetooth && navigator.bluetooth.requestDevice); },
  async add() {
    if (!this.supported()) { btHint(isIOS() ? t('bt.iosAdd') : t('bt.noneAdd'), true); return; }
    let dev;
    try {
      dev = await navigator.bluetooth.requestDevice({
        filters: [{ services: [UUID.ftms] }, { services: [UUID.cp] }, { services: [UUID.csc] }, { services: [UUID.hr] }],
        optionalServices: [UUID.ftms, UUID.cp, UUID.csc, UUID.hr]
      });
    } catch (e) {
      if (e.name === 'NotFoundError') return; // окно выбора закрыто
      btHint(e.name === 'SecurityError' ? t('bt.blocked') : t('bt.pickFailed', { msg: e.message }), true); return;
    }
    if (this.devs.some(d => d.dev.id === dev.id)) { btHint(t('bt.already')); return; }
    const d = new BLEDev(dev); this.devs.push(d); this.changed();
    try {
      await d.connect();
      btHint(d.roles.has('trainer') ? (d.ctrl ? t('bt.trainerCtrl') : t('bt.trainerNoCtrl')) : d.roles.has('hr') && d.roles.size === 1 ? t('bt.hrOk') : t('bt.connected', { name: d.name }));
    } catch (e) { this.devs = this.devs.filter(x => x !== d); this.changed(); btHint(t('bt.failed'), true); }
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
// Управление сопротивлением: шлём уклон маршрута не чаще раза в секунду и только при изменении
const Trainer = {
  last: -10, sent: null,
  update(t, grade) {
    const d = Sensors.trainer(); if (!d || !d.ctrl) return;
    const target = Math.round(grade * settings.difficulty / 100 * 10) / 10; // проценты уклона с учётом сложности
    if (t - this.last < 1) return;
    if (this.sent !== null && Math.abs(target - this.sent) < .2 && t - this.last < 5) return;
    this.last = t; d.setGrade(target).then(ok => { if (ok) this.sent = target; });
  },
  info() { const d = Sensors.trainer(); return d && d.ctrl && this.sent != null ? this.sent : null; }
};
function isIOS() { return /iP(hone|ad|od)/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1); }
function btHint(t, warn) { const h = $('#btHint'); h.textContent = t; h.classList.toggle('warn', !!warn); }
function renderDevs() {
  const ul = $('#devList'); ul.innerHTML = '';
  Sensors.devs.forEach(d => {
    const li = document.createElement('li'); li.className = 'dev';
    const tags = ROLE_NAMES.filter(r => d.roles.has(r[0])).map(r => '<span class="tag on">' + r[1] + '</span>').join('') + (d.roles.has('trainer') && !d.ctrl && d.status === 'online' ? '<span class="tag">' + t('dev.noCtrlTag') + '</span>' : '') || '<span class="tag">' + t('dev.detecting') + '</span>';
    li.innerHTML = '<div><b></b><br><small></small><div class="tags">' + tags + '</div></div>';
    li.querySelector('b').textContent = d.name; li.querySelector('small').textContent = d.status === 'online' ? t('dev.online') : d.status === 'reconnecting' ? t('dev.reconnecting') : t('dev.connecting');
    const btn = document.createElement('button'); btn.className = 'btn'; btn.type = 'button'; btn.textContent = t('dev.disconnect'); btn.onclick = () => Sensors.remove(d);
    li.appendChild(btn); ul.appendChild(li);
  });
}
