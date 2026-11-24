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
// The settings with the member's account, so every device they sign in on shows the same: of the account's copy
// and this browser's, the one changed later wins (settings.saved, the page's clock). Settings this browser never
// changed are not sent: a fresh browser's defaults must not take the place of what the member chose elsewhere.
const SettingsSync = {
  timer: null,
  async pull() {
    let kept; try { kept = await Site.get('/settings'); } catch (e) { return; }
    if ((kept.saved_at || 0) > (settings.saved || 0)) takeSettings(kept.settings, kept.saved_at);
    else if (store.get('settings', null) !== null && (settings.saved || 1) > (kept.saved_at || 0)) this.push();
  },
  later() { clearTimeout(this.timer); this.timer = setTimeout(() => this.push(), 1500); },
  push() {
    if (!settings.saved) settings.saved = 1; // changed before the account kept them: older than any copy it has
    Site.req('PUT', '/settings', { settings, saved_at: settings.saved })
      .then(kept => { if (kept && (kept.saved_at || 0) > (settings.saved || 0)) takeSettings(kept.settings, kept.saved_at); })
      .catch(() => {});
  }
};
// the address the reader sees: the site's page that frames the trainer, or the trainer itself
function topPath() { try { return window.top.location.pathname + window.top.location.search; } catch (e) { return location.pathname + location.search; } }
