'use strict';
/* ---------------- Сайт: личный кабинет и совместная езда через /api/v1/virtual-ride/ ---------------- */
// Страница открыта во фрейме сайта и говорит с его API от имени вошедшего участника (сессия + CSRF).
const API_BASE = '/api/v1/virtual-ride';
const Site = {
  csrf() { const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/); return m ? decodeURIComponent(m[1]) : ''; },
  async req(method, path, body) {
    const headers = { 'Accept': 'application/json' };
    if (body) headers['Content-Type'] = 'application/json';
    if (method !== 'GET') headers['X-CSRFToken'] = this.csrf();
    const r = await fetch(API_BASE + path, { method, credentials: 'same-origin', headers, body: body ? JSON.stringify(body) : undefined });
    if (r.status === 204) return null;
    const data = await r.json().catch(() => null);
    if (!r.ok) { const e = new Error((data && (data.detail || data.message)) || ('HTTP ' + r.status)); e.status = r.status; throw e; }
    return data;
  },
  get(p) { return this.req('GET', p); },
  post(p, b) { return this.req('POST', p, b || {}); },
  loginHref() { return (Records.loginUrl || '/accounts/login/') + '?next=' + encodeURIComponent(topPath()); }
};
// The settings with the member's account, so every device they sign in on shows the same. The account stamps each
// copy by the site's clock; this browser remembers whose account its copy goes with (settings.owner), the stamp of
// the copy it last had (settings.synced) and whether it changed anything since (settings.unsent). Its changes replace
// the account's copy only if that is still the one it had; otherwise another device saved later, and its copy comes
// here. A browser that never changed anything sends nothing: its defaults must not take the place of what the member
// chose elsewhere; nor does a browser another member used send that member's settings into this one's account.
const SettingsSync = {
  timer: null, changes: 0, busy: false, again: false,
  me() { return Records.me && Records.me.user_id; },
  async pull() {
    let kept; try { kept = await Site.get('/settings'); } catch (e) { return; }
    if (settings.owner !== this.me()) {
      if ((kept.saved_at || 0) > 0) takeSettings(kept.settings, kept.saved_at);
      // kept here before the account kept anything: they go to an account still empty
      else if (settings.owner == null && store.get('settings', null) !== null) this.push();
      return;
    }
    if (settings.unsent) this.push();
    else if ((kept.saved_at || 0) > (settings.synced || 0)) takeSettings(kept.settings, kept.saved_at);
  },
  later() { this.changes++; clearTimeout(this.timer); this.timer = setTimeout(() => this.push(), 1500); },
  // one at a time: a second copy sent before the first is answered would be behind it, and refused
  push() {
    if (this.busy) { this.again = true; return; }
    this.busy = true; this.again = false;
    const { synced, unsent, owner, ...own } = settings, sent = this.changes, me = this.me();
    Site.req('PUT', '/settings', { settings: own, base: owner === me ? synced || 0 : 0 }).then(kept => {
      if (!kept.accepted) { takeSettings(kept.settings, kept.saved_at); return; }
      Object.assign(settings, { owner: me, synced: kept.saved_at }); if (this.changes === sent) settings.unsent = false;
      store.set('settings', settings);
    }).catch(() => {}).finally(() => { this.busy = false; if (this.again) this.push(); });
  }
};
// the address the reader sees: the site's page that frames the trainer, or the trainer itself
function topPath() { try { return window.top.location.pathname + window.top.location.search; } catch (e) { return location.pathname + location.search; } }
