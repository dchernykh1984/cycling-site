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
// the address the reader sees: the site's page that frames the trainer, or the trainer itself
function topPath() { try { return window.top.location.pathname + window.top.location.search; } catch (e) { return location.pathname + location.search; } }
