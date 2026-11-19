'use strict';
/* ---------------- Workouts planned in intervals.icu (issue #471): picked on the plan screen, ridden by power ---------------- */
// The list is read when the page learns the member connected intervals.icu, and a workout's steps when it is
// picked: the site keeps neither, nor the FTP they were turned into watts with. The page remembers only which
// one was picked (settings.planIcu), so a reload picks it again while it is still planned.
const Icu = { list: null, failed: '', plan: null, pickFailed: '' };
// the rider's own today, as their calendar at intervals.icu counts days
const localDay = d => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
// a planned day (YYYY-MM-DD) in the words of the page: the weekday, the day and the month
function fmtDay(iso) {
  const [y, m, d] = String(iso).split('-').map(Number);
  return y && m && d ? new Date(y, m - 1, d).toLocaleDateString(LOCALE, { weekday: 'short', day: 'numeric', month: 'short' }) : '';
}
function icuOn() { const who = Records.me; return !!(who && who.authenticated && who.intervals_connected); }
// the workout picked to ride, or null for the own plan by gears and cadence
function icuPicked() { return icuOn() && settings.planIcu != null ? settings.planIcu : null; }
async function loadIcuWorkouts() {
  if (!icuOn()) { renderIcu(); return; }
  Icu.list = null; Icu.failed = ''; renderIcu();
  try { Icu.list = await Site.get('/intervals/workouts?oldest=' + localDay(new Date())); } catch (e) { Icu.list = []; Icu.failed = e.message; }
  // a workout picked before and no longer planned gives way to the own plan
  if (Icu.list.some(w => w.id === settings.planIcu)) pickIcu(settings.planIcu); else pickIcu(null);
}
async function pickIcu(id) {
  settings.planIcu = id; store.set('settings', settings); Icu.plan = null; Icu.pickFailed = ''; renderIcu();
  if (id == null) return;
  try {
    const w = await Site.get('/intervals/workouts/' + id);
    if (settings.planIcu !== id) return; // another was picked while this one loaded
    Icu.plan = { name: w.name, ftp: w.ftp_w, cues: w.cues, steps: w.steps.map(s => ({ min: s.duration_s / 60, w: s.power_w, w2: s.power_end_w, cad: s.cadence_rpm })) };
  } catch (e) { if (settings.planIcu === id) Icu.pickFailed = e.message; }
  renderIcu();
}
function renderIcu() {
  const on = icuOn(), picked = icuPicked();
  $('#plIcu').classList.toggle('hidden', !on); $('#plOwn').classList.toggle('hidden', picked != null);
  if (on) {
    $('#plIcuHint').textContent = Icu.list == null ? t('icu.loading') : Icu.failed ? t('icu.failed', { msg: Icu.failed }) : Icu.list.length ? t('icu.list') : t('icu.none');
    const box = $('#plIcuList'); box.textContent = '';
    const option = (id, name, meta) => {
      const b = document.createElement('button'); b.type = 'button'; b.className = 'route'; b.setAttribute('aria-pressed', id === picked ? 'true' : 'false');
      b.innerHTML = '<b></b><span class="meta"></span>'; b.querySelector('b').textContent = name; b.querySelector('.meta').textContent = meta;
      b.onclick = () => pickIcu(id); box.appendChild(b);
    };
    option(null, t('plan.mine'), '');
    (Icu.list || []).forEach(w => option(w.id, w.name || '—', fmtDay(w.date) + (w.duration_s ? ' · ' + fmtTime(w.duration_s) : '')));
    const chosen = (Icu.list || []).find(w => w.id === picked), name = chosen ? chosen.name : '';
    $('#plIcuInfo').textContent = picked == null ? '' : Icu.pickFailed ? t('icu.pickFailed', { name, msg: Icu.pickFailed }) : !Icu.plan ? t('icu.loadingOne', { name })
      : t('icu.picked', { name: Icu.plan.name, n: Icu.plan.steps.length, t: fmtTime(planSeconds(Icu.plan.steps)) }) + (Icu.plan.ftp ? t('icu.ftp', { w: Icu.plan.ftp }) : '');
  }
  if (phase === 'menu') renderStartSum();
}
const planSeconds = steps => steps.reduce((a, s) => a + s.min * 60, 0);
// what a plan ride rides: the picked workout once loaded, else the own plan
function planToRide() {
  return icuPicked() != null && Icu.plan ? { steps: Icu.plan.steps, cues: Icu.plan.cues, name: Icu.plan.name } : { steps: settings.plan.steps, cues: [], name: null };
}
// a picked workout still loading, or one that failed to: no plan ride starts until it is there or another is picked
const planWaits = () => icuPicked() != null && !Icu.plan;
function planSummary() {
  return icuPicked() != null && Icu.plan ? t('sum.icu', { name: Icu.plan.name, t: fmtTime(planSeconds(Icu.plan.steps)) }) : t('sum.plan', { t: fmtTime(planTotalMin() * 60) });
}
