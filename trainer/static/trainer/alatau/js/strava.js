'use strict';
/* ---------------- Strava: every finished ride goes there as a virtual ride, once the member allows it ---------------- */
const STRAVA_LOGO = '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M15.387 17.944l-2.089-4.116h-3.065L15.387 24l5.15-10.172h-3.066m-7.008-5.599l2.836 5.598h4.172L10.463 0l-7 13.828h4.169"/></svg>';
// on the setup page: an offer to connect Strava, or, once connected, that the rides go there and where to manage it
function renderStravaNote() {
  const el = $('#stravaNote'), who = Records.me, on = !!(who && who.authenticated && who.strava_available);
  el.classList.toggle('hidden', !on); if (!on) return;
  el.textContent = '';
  const text = document.createElement('span'), a = document.createElement('a');
  a.target = '_top';
  if (who.strava_connected) {
    // the member's box on the profile decides whether rides go there (issue #471)
    text.textContent = who.strava_send ? t('strava.on') : t('strava.off'); a.href = Records.accountUrl + '#virtual-rides-strava'; a.textContent = t('strava.manage');
  } else {
    a.className = 'strava-btn'; a.innerHTML = STRAVA_LOGO + '<span>Connect with Strava</span>';
    a.href = langPath(who.strava_connect_url) + '?next=' + encodeURIComponent(topPath());
    text.textContent = t('strava.offer');
  }
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

/* ---------------- intervals.icu: connected on the profile with the member's own key (issue #471) ---------------- */
// on the setup page: whether rides go there, and where to connect it or turn the sending on or off
function renderIntervalsNote() {
  const el = $('#intervalsNote'), who = Records.me, on = !!(who && who.authenticated && who.intervals_available);
  el.classList.toggle('hidden', !on); if (!on) return;
  el.textContent = '';
  const text = document.createElement('span'), a = document.createElement('a');
  a.target = '_top'; a.href = Records.accountUrl + '#virtual-rides-intervals';
  if (who.intervals_connected) { text.textContent = who.intervals_send ? t('intervals.on') : t('intervals.off'); a.textContent = t('intervals.manage'); }
  else { text.textContent = t('intervals.offer'); a.textContent = t('intervals.connect'); }
  el.append(text, ' ', a);
}
// what happened to a saved ride at intervals.icu: an activity to open, or why not and another try
let intervalsFor = null; // the ride the results show: a late answer about an earlier one is dropped
function intervalsShow(rideId, s) {
  intervalsFor = rideId;
  const el = $('#resIntervals');
  el.classList.toggle('hidden', !s); if (!s) return;
  el.textContent = '';
  if (s.status === 'done') {
    const a = document.createElement('a'); a.href = s.activity_url; a.target = '_blank'; a.rel = 'noopener'; a.className = 'strava-link'; a.textContent = t('intervals.view');
    el.append(t('intervals.done') + ' ', a); return;
  }
  const b = document.createElement('button'); b.className = 'btn'; b.type = 'button'; b.textContent = t('intervals.retry');
  // one try at a time: whether intervals.icu drops a second copy of an activity is not documented
  b.onclick = () => { b.disabled = true; Site.post('/rides/' + rideId + '/intervals').then(r => { if (intervalsFor === rideId) intervalsShow(rideId, r); })
    .catch(e => { if (intervalsFor === rideId) intervalsShow(rideId, { status: 'failed', error: e.message }); }); };
  el.append(t('intervals.failed', { msg: s.error }) + ' ', b);
}
