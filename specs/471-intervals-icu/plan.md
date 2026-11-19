# Implementation Plan: Workouts from intervals.icu, rides sent where the member chooses, a truer ride

**Spec**: `spec.md` (issue #471)
**Branch**: `471-intervals-icu`, one pull request per phase

## Summary

Three phases, each its own pull request.

1. **Services.**
   - The profile shows each service as connected or not, with a box to send rides there.
   - intervals.icu is connected with the member's API key, which is kept encrypted.
   - Rides go to intervals.icu as they go to Strava.
2. **Workouts.**
   - The trainer page lists the workouts planned in intervals.icu and rides one.
   - A smart trainer holds the target watts (ERG), and SIM stays for everything else.
3. **Mechanics.**
   - The air density follows the route's height.
   - Riding close behind someone saves effort, and the smart trainer feels it too.
   - A rider with only a cadence sensor slows on climbs in races and free rides.

## Constitution Check

- **IV (languages).** The site's new strings are in the catalogues, in ru / kk / en. The trainer
  page's own strings stay in its ru / kk / en dictionary, the exception recorded in
  `specs/site/site-shell.md`.
- **VI (anywhere).** intervals.icu is a named provider with its own setting, and nothing in the code
  assumes a place.
- **VII (API).**
  - Every new operation is an API operation: the services, connecting intervals.icu, the uploads
    and, in phase 2, the workouts.
  - Connecting Strava stays the recorded browser round trip.
- **VIII (one fact, one home).** FTP, zones and workouts live in intervals.icu. The site keeps only
  what it needs to send rides there.
- **IX (nothing lost).** A ride's track is kept with it, so an upload can be sent again.
- **X (checked, private).**
  - The intervals.icu key is encrypted at rest and never leaves the server.
  - The inputs are bounded.
  - The privacy policy names intervals.icu.
- **XI (API promises).** New endpoints and optional fields only. `strava_connected` keeps its
  meaning.
- **XII (any screen).** The new controls are named in every language and big enough to tap on a
  phone.
- **XIV (explain where met).** The connect form says where intervals.icu shows the key, and what
  connecting does.

## Research

The intervals.icu API, read on 2026-11-19 from the forum guide
(https://forum.intervals.icu/t/api-access-to-intervals-icu/609) and the OpenAPI document
(https://intervals.icu/api/v1/docs):

- **Authentication.**
  - HTTP Basic, with the username `API_KEY` and the member's key as the password.
  - In any path the athlete id `0` means the key's own athlete.
  - `GET /api/v1/athlete/0` returns the athlete with `id` (such as `i12345`), `name` and
    `sportSettings`. It checks a key and names its athlete in one call.
- **Upload.**
  - `POST /api/v1/athlete/{id}/activities`, with the multipart field `file` and the query
    parameters `name`, `description`, `device_name` and `external_id`.
  - The answer carries the new `id` and `activities`.
  - The accepted formats are not documented. The site sends the TCX it already builds for Strava,
    uncompressed, and the first live upload confirms it.
- **The calendar.**
  - `GET /api/v1/athlete/{id}/events`, with `oldest` and `newest` (`yyyy-MM-dd`, required) and
    `category=WORKOUT`.
  - An event has `id`, `start_date_local`, `type`, `name`, `moving_time`, `icu_ftp` and
    `workout_doc`.
  - The steps of `workout_doc` are not documented, so the design does not rely on them.
- **A workout's steps.**
  - `GET /api/v1/athlete/{id}/events/{eventId}/download.zwo` returns the workout in Zwift's
    published ZWO form. It has warm-ups, cool-downs, ramps, steady states, repeated intervals, free
    rides, cadence and text cues, with power as a fraction of FTP.
  - FTP comes from the event's `icu_ftp`, else from the athlete's `sportSettings` for rides.
- **Limits and transport.**
  - 5000 calls a day and 2500 in any 15 minutes per key, plus 10 a second per address. An overflow
    answers 429 with Retry-After.
  - Cloudflare may challenge a client with a default library user agent, so the site sends its own
    name.
  - CORS is not documented. The key must not reach a browser anyway, so every call goes through the
    site.

## Design

### Phase 1 -- services

**Settings.** `INTEGRATIONS_ENCRYPTION_KEY`, a Fernet key. Without it, intervals.icu is not
offered. `cryptography` becomes a direct dependency: it is already installed, but only as another
package's dependency.

**Models** (`trainer/models.py`):

- `StravaConnection.send_rides`, BooleanField, default True. The existing rows get True from the
  migration's default.
- `IntervalsConnection`:
  - the member (one to one);
  - `athlete_id` and `athlete_name`;
  - `api_key`, encrypted text;
  - `send_rides`, default False;
  - `connected_at`.
- `IntervalsUpload`:
  - the ride (one to one, primary key);
  - `status`: processing, done or failed;
  - `activity_id`, `error` and `updated_at`;
  - an `activity_url` property, `https://intervals.icu/activities/<id>`.

**`trainer/secret_box.py`.** `seal(text)` and `open_sealed(token)` wrap Fernet with the setting.
`open_sealed` returns None for a token it cannot read: a lost or changed key reads as not connected.

**`trainer/intervals.py`**, built like `trainer/strava.py`. Every call goes through `requests`,
which the tests patch.

- `available()`.
- `connect(user, key, send_rides)`: `GET /athlete/0` with the key, then the stored connection.
- `disconnect(connection)`.
- `upload(ride)`: the TCX is `strava.tcx()` decompressed. A 401 or 403 drops the connection and
  records the failure.

**Saving a ride** (`api/endpoints/virtual_ride.py`). A ride that is not in demo mode and has its
track goes to Strava when connected with its box on, and to intervals.icu when connected with its
box on.

**API** (`/api/v1/virtual-ride/`):

- `GET /services` and `PATCH /services/{strava|intervals}` with `{send_rides}`.
- `POST /services/intervals` with `{api_key, send_rides}` (201, or 422 with intervals.icu's reason,
  or 429 past five keys in ten minutes),
  and `DELETE /services/intervals`.
- `POST /rides/{id}/intervals` and `GET /rides/{id}/intervals`, mirroring Strava's.
- `GET /me` gains `intervals_available`, `intervals_connected`, `strava_send` and `intervals_send`.

**Profile.**

- The card's Strava block becomes a services block.
- Each service shows its state and box. Changing a box saves at once: a small form, a POST to a view
  that also answers the API's PATCH rules.
- intervals.icu has a key field, a link to its settings and "Connect"; once connected, "Disconnect".
- Recent rides link "View on intervals.icu" beside "View on Strava".

**Trainer page.** The results show intervals.icu's status beside Strava's (`strava.js` grows a
sibling), with "Send again".

**Specs and documents.**

- `specs/site/accounts.md`: FR-ACC-007 gains an intervals.icu sibling.
- `specs/site/api.md`.
- The privacy policy.
- `README.md` and `.env.example`: the new setting.

**Tests.**

- The secret box, including a wrong key reading as None.
- Connect, with a refused key and an accepted one.
- Upload: done, failed, unauthorized drops the connection, unavailable.
- The boxes, and the migration's default for existing Strava rows.
- Every API operation, with its rights.
- The profile's block in every state.
- The trainer page's results, in an e2e test.

### Phase 2 -- workouts and ERG

**Listing workouts.** `GET /api/v1/virtual-ride/intervals/workouts` reads the events from today to
seven days ahead with `category=WORKOUT`, keeps the cycling ones, and answers their id, date, name
and duration.

**Loading a workout.** `GET .../intervals/workouts/{eventId}` downloads the ZWO and parses it safely
(defusedxml, or a bounded parser). It turns each element into steps, with power in watts from the
FTP:

- SteadyState, Warmup, Cooldown and Ramp;
- IntervalsT, which repeats;
- FreeRide;
- Cadence and textevent.

**The trainer page.**

- The plan model accepts power steps beside gear steps.
- The display shows the target in watts.
- `bluetooth.js` sends FTMS Set Target Power (0x05) where the trainer reports Power Target Setting.
  It falls back to SIM (0x11) on steps without power and when the rider switches ERG off.

**Saving.** The saved ride is a plan ride. FTP and the workout are not stored.

### Phase 3 -- mechanics

- **Air density.** Density from the height by the International Standard Atmosphere (ISO 2533),
  replacing the fixed 1.08 kg/m3.
- **Drafting.**
  - The drag of a rider close behind another, bot or live member, shrinks with the gap along the
    route, by a curve from published wind-tunnel measurements. The source is cited in the code and
    in the pull request.
  - In SIM mode, Cw sent to a smart trainer is the reduced one.
- **Cadence-only riders.** The cadence-only speed setting defaults to the physics in races and free
  rides. Plans by gear keep the gear's speed, whatever the setting.

## Rollout

- **The encryption key.** The maintainer generates the key and adds it on Render as
  `INTEGRATIONS_ENCRYPTION_KEY`. Without it, intervals.icu is not offered, and nothing else changes.
- **Deploys.** Each phase is deployed at night by the nightly deploy, like any merge.
