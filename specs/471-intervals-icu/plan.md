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
- `upload(ride)`: the TCX is `strava.tcx()` decompressed. A 401 drops the connection and records
  the failure. A 403 only records it: the Cloudflare proxy in front of intervals.icu answers 403 when
  it turns an address away, which says nothing about the key.

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

### Phase 2 -- workouts and ERG (as built)

**Listing workouts.** `GET /api/v1/virtual-ride/intervals/workouts?oldest=` reads
`/athlete/{id}/events` with `oldest`, `newest` (eight days) and `category=WORKOUT`.
- `oldest` is the rider's own today, which the page sends; without it, the site's today.
- Only intervals.icu's cycling types are kept: Ride, VirtualRide, MountainBikeRide, GravelRide,
  TrackRide, Cyclocross, EBikeRide, EMountainBikeRide (its sport enum).
- Each comes as its id, date, name and duration, by date, at most fifty.

**Loading a workout.** `GET .../intervals/workouts/{id}` reads the event and refuses one that is not a
cycling `WORKOUT` (404). It then downloads `download.zwo`, asking for any type rather than JSON.
- The FTP is the event's `icu_ftp`, else the indoor FTP of the member's ride settings, else their
  FTP; a file's own `ftpOverride` wins. A workout by power with no FTP at all is refused with where
  to set one.
- `trainer/zwo.py` parses the file with defusedxml, no DTD, at most 512 KB. Power is a share of FTP.
  `Warmup`, `Cooldown` and `Ramp` go from `PowerLow` at their start to `PowerHigh` at their end, as
  the reference's examples say. A range on a steady step is ridden at its middle. `IntervalsT`
  unfolds into its repeats, with `Cadence` on and `CadenceResting` off. `FreeRide`, `MaxEffort` and
  a step this page does not know keep their time without power. A `textevent` falls `timeoffset`
  seconds into the element holding it.
- Bounds: six hours (a ride's track), 500 steps, 100 repeats, 200 cues of 200 characters, 3000 W,
  cadence 20-200 rpm.

**Reads** are held to sixty a member in ten minutes (429): each is one to three calls from the
site's one address. A key no longer taken drops the connection (409); a workout without steps, or
by power with no FTP, is 422, since trying again changes nothing; intervals.icu failing is 503.

**The trainer page.**
- `js/workouts.js` lists the workouts beside "My plan by gears and cadence" and loads the picked one.
  Only its id is kept in the browser.
- `Work` (`js/ride.js`) takes a workout's steps (`w`, `w2`, `cad`, `min`) beside gear steps.
  `Work.target()` gives the power this second. The time on target counts power within 5 %, or else
  cadence within 5 rpm. Cues reach the page as `planCue`.
- The HUD shows the target in watts (a ramp's end, "ERG" when the trainer holds it) and colours the
  power and the cadence against it. The results show each step's average power and its share on
  target.
- The demo rides a workout's power. A rider by cadence or speed sees the target beside their
  estimated power.

**ERG.**
- `bluetooth.js` reads the Fitness Machine Feature (0x2ACC): bit 3 of its second field is Power
  Target Setting. It then reads the Supported Power Range (0x2AD8) and clamps to it.
- While ERG is on and the step sets a power, it sends Set Target Power (0x05) at most once a second,
  again every five seconds. Otherwise, and in the menu, it sends the grade (0x11).
- The HUD's ERG switch (on by default, kept in the browser) turns it off.

**Saving.** The ride is a plan ride. Neither the workout nor the FTP is stored.

### Phase 3 -- mechanics (as built)

**Air density.** `airDensity(h)` (`js/physics.js`) is the International Standard Atmosphere's
(ISO 2533): 1.225 kg/m3 at sea level and 15 C, the air cooling 6.5 C a kilometre, so
rho = 1.225 * (1 - 0.0065 h / 288.15) ^ 4.25588. Each step takes it at the height of the road under
each rider. It replaces the fixed 1.08 kg/m3: at 930 m the air is 1.119 kg/m3, at 3000 m 0.909.

**Drafting.**
- **The source.** On-site measurements of riders pedalling at 45 km/h through a stereo-PIV system
  (Spoelstra, Mahalingesh, Sciacchitano 2020, "Drafting Effect in Cycling: On-Site Aerodynamic
  Investigation by the 'Ring of Fire'", Proceedings 49(1):113, doi:10.3390/proceedings2020049113,
  CC BY). In line 0.7 m behind the wheel the trailing rider's drag is 45 % lower; 1.3 points more for
  each 10 cm closer, 3.9 points less for each 10 cm aside. They measured 0.35-0.85 m back and up to
  0.2 m aside.
- **The assumption.** Further out the same slopes are assumed, and no open measurement checks it:
  the saving is gone 4.2 m behind the wheel, or 1.2-1.4 m aside by the gap. The open papers read for this go
  no further back than 1 m (Blocken et al. 2013); those that may (Kyle 1979, Olds 1998) are not open.
- **Why this source.** It measured real riders pedalling on the road. Blocken et al. 2013 (Computers
  & Fluids 71:435-445) computed 12-27 % by position, from 1 cm to 1 m, with still legs and wheels and
  the body without a bicycle. They name that as why their figure is below the 37-49 % measured
  earlier in a wind tunnel (Zdravkovich et al. 1996), and they cite Kyle's coast-down tests (1979) at
  38 %.
- **The gap.** The bikes as drawn are 1.71 m from tyre to tyre, so the gap between the wheels is the
  distance between two riders less 1.71 m. On a loop, a rider just behind is a lap ahead.
- **Who.** The rider and the bots alike ride in the best wake ahead: a bot's, the rider's or a live
  member's. The leader's own saving (0.8-2.6 % at 1 cm, Blocken et al. 2013) is left out.
- **SIM.** A smart trainer is sent Cw = CdA x (1 - the share) x the air's density. A change of
  0.01 kg/m, the unit it reads, is sent within the second, as a change of the grade is.

**Cadence-only riders.** A cadence sensor alone rides by the physics, from the trainer's power curve,
unless the rider chose the gear's speed. A step of the own plan by gears rides at its gear's speed,
whatever the choice. The gear's speed was the default, and stored settings cannot tell a rider who
picked it from one who never looked. So every rider is moved to the physics once (`cadPhysics`), and
one who picks the gear's speed again keeps it.

**Tests** (`tests/e2e/test_virtual_ride.py`):
- the density against the standard's table at 0, 1000, 2000 and 3000 m;
- the share saved in line, closer, aside, alongside, far behind and in front;
- the speed a wake gives at 200 W, and a bot in the rider's wake;
- a smart trainer told the lighter drag within the second;
- which speed a cadence sensor rides by, and the default moved once.

## Rollout

- **The encryption key.** The maintainer generates the key and adds it on Render as
  `INTEGRATIONS_ENCRYPTION_KEY`. Without it, intervals.icu is not offered, and nothing else changes.
- **Deploys.** Each phase is deployed at night by the nightly deploy, like any merge.
