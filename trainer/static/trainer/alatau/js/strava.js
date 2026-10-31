'use strict';
/* ---------------- Strava: every finished ride goes there as a virtual ride, once the member allows it ---------------- */
const MAX_TRACK = 6 * 3600; // the site keeps six hours of a ride's track, a point a second
const STRAVA_LOGO = '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M15.387 17.944l-2.089-4.116h-3.065L15.387 24l5.15-10.172h-3.066m-7.008-5.599l2.836 5.598h4.172L10.463 0l-7 13.828h4.169"/></svg>';
// [t_s, lat, lon, ele_m, distance_m, speed_ms, power_w, cadence_rpm, hr_bpm]: the route's place on the map, not a GPS fix
function trackPoint(inp) {
  const o = riderPos(me, {}), ll = unproj(o.px, o.pz);
  return [Math.round(raceT * 10) / 10, +ll.lat.toFixed(6), +ll.lon.toFixed(6), Math.round(o.y * 10) / 10, Math.round(me.stats.dist * 10) / 10,
    Math.round(clamp(me.v, 0, 40) * 100) / 100, Math.round(clamp(inp.P || 0, 0, 3000)), Math.round(clamp(inp.cad || 0, 0, 250)), Math.round(clamp(Sensors.hr() || 0, 0, 260))];
}
// on the setup page: an offer to connect Strava, to a member who has not; turning it off is the profile's
function renderStravaNote() {
  const el = $('#stravaNote'), who = Records.me, on = !!(who && who.authenticated && who.strava_available && !who.strava_connected);
  el.classList.toggle('hidden', !on); if (!on) return;
  el.textContent = '';
  const text = document.createElement('span'), a = document.createElement('a');
  a.target = '_top'; a.className = 'strava-btn'; a.innerHTML = STRAVA_LOGO + '<span>Connect with Strava</span>';
  a.href = langPath(who.strava_connect_url) + '?next=' + encodeURIComponent(topPath());
  text.textContent = t('strava.offer');
  el.append(text, a);
}
// what happened to a saved ride at Strava: processing, an activity to open, or why not and another try
let stravaFor = null; // the ride the results show: a late answer about an earlier one is dropped
function stravaShow(rideId, s, tries = 0) {
  if (tries === 0) stravaFor = rideId; else if (stravaFor !== rideId) return;
  const el = $('#resStrava');
  el.classList.toggle('hidden', !s); if (!s) return;
  el.textContent = '';
  if (s.status === 'done') {
    const a = document.createElement('a'); a.href = s.activity_url; a.target = '_blank'; a.rel = 'noopener'; a.className = 'strava-link'; a.textContent = 'View on Strava';
    el.append(t('strava.done') + ' ', a); return;
  }
  if (s.status === 'failed') {
    const b = document.createElement('button'); b.className = 'btn'; b.type = 'button'; b.textContent = t('strava.retry');
    b.onclick = () => Site.post('/rides/' + rideId + '/strava').then(r => stravaShow(rideId, r)).catch(e => stravaShow(rideId, { status: 'failed', error: e.message }));
    el.append(t('strava.failed', { msg: s.error }) + ' ', b); return;
  }
  // half a minute of asking is enough: past it the page says so instead of seeming to wait for ever
  if (tries >= 15) { el.textContent = t('strava.later'); return; }
  el.textContent = t('strava.processing');
  setTimeout(() => Site.get('/rides/' + rideId + '/strava').then(r => stravaShow(rideId, r, tries + 1)).catch(() => {}), 2000);
}
