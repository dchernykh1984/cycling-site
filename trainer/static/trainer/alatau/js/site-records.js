'use strict';
const RECORD_LABELS = { route_first: t('rec.firstLabel'), route_best: t('rec.bestLabel'), peak_5s_w: t('rec.peakLabel', { d: durLabel(5) }), peak_1m_w: t('rec.peakLabel', { d: durLabel(60) }), peak_5m_w: t('rec.peakLabel', { d: durLabel(300) }), peak_20m_w: t('rec.peakLabel', { d: durLabel(1200) }), max_speed_kmh: t('rec.maxSpeedLabel') };
function bestPeaks(powerLog) {
  const out = {};
  PEAKS.forEach(([k, sec]) => {
    if (powerLog.length < sec) return;
    let sum = 0, best = 0; for (let i = 0; i < powerLog.length; i++) { sum += powerLog[i]; if (i >= sec) sum -= powerLog[i - sec]; if (i >= sec - 1) best = Math.max(best, sum / sec); }
    out[k] = Math.round(best);
  });
  return out;
}
// Ответ сервера о рекордах заменяет местный: он сравнивает со всеми заездами в личном кабинете
function showServerRecords(keys, ride, peaks) {
  const W = ' ' + t('u.w'), val = { route_first: fmtTime(ride.time), route_best: fmtTime(ride.time), peak_5s_w: peaks.p5 + W, peak_1m_w: peaks.p60 + W, peak_5m_w: peaks.p300 + W, peak_20m_w: peaks.p1200 + W, max_speed_kmh: fmt1(ride.maxSpeed) + ' ' + t('u.kmh') };
  const items = (keys || []).filter(k => RECORD_LABELS[k]).map(k => RECORD_LABELS[k] + ': ' + val[k]);
  const box = $('#resRec');
  box.innerHTML = items.length ? '<b>' + t('rec.newInProfile') + '</b><ul>' + items.map(t => '<li>' + t + '</li>').join('') + '</ul>' : '';
  box.classList.toggle('hidden', !items.length);
}
// Сводка с сервера в том же виде, в каком «Мои рекорды» хранят её в браузере
function recordsFromServer(sum, rides, plan) {
  const routes = {};
  (sum.routes || []).forEach(r => { routes[r.route] = { time: r.duration_s, date: Date.parse(r.finished_at), attempts: r.attempts, avgPower: r.best_avg_power_w }; });
  const keyOf = { peak_5s_w: 'p5', peak_1m_w: 'p60', peak_5m_w: 'p300', peak_20m_w: 'p1200' }, peaks = {};
  Object.keys(keyOf).forEach(k => { if (sum.peaks && sum.peaks[k]) peaks[keyOf[k]] = { w: sum.peaks[k] }; });
  return {
    v: 1, routes, peaks, plan,
    maxSpeed: sum.max_speed_kmh ? { v: sum.max_speed_kmh } : null,
    totals: { rides: sum.rides, dist: sum.distance_km, gain: sum.elevation_m, time: sum.time_s },
    history: (rides || []).map(h => ({ id: 's' + h.id, date: Date.parse(h.finished_at), kind: h.kind === 'race' ? undefined : h.kind, route: h.route, time: h.duration_s, avgSpeed: h.avg_speed_kmh, avgPower: h.avg_power_w || 0, place: h.place || 1, of: h.field_size || 1, demo: h.power_source === 'demo' }))
  };
}
