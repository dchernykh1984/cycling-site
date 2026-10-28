# Implementation Plan: Virtual ride together, saved to the profile

**Branch**: `392-virtual-ride-multiplayer` | **Spec**: [spec.md](spec.md)

## Summary

The trainer page (`trainer/static/trainer/alatau.html`) stays one self-contained file in the site's
frame and talks to `/api/v1/virtual-ride/` with the member's session. The site stores rides, group
races and who is on the page (`trainer` app); records are computed (`trainer/records.py`), riding
together is polling (`trainer/live.py`, no socket server), Strava is an adapter over `requests`
(`trainer/strava.py`). The voice chat was taken out again (the spec's User Story 6).

## Constitution Check

- **IV (languages)**: the page's texts live in a ru / kk / en dictionary inside the page, not in the
  catalogues -- an exception recorded in `specs/site/site-shell.md`, so the page stays one file its
  author can edit. The site's own strings are in the catalogues. Strava's "Connect with Strava" and
  "View on Strava" keep the wording its brand guidelines require.
- **VI (anywhere)**: the routes, landmarks and kit are Almaty's, written into the page (listed under
  "Local assumptions"); Strava is a named provider with its own settings.
- **VII (API)**: every page operation is an API operation; connecting Strava is the recorded
  exception (a browser round trip through Strava).
- **VIII (one fact, one home)**: records derived, never stored; the Strava client id and secret are
  the sign-in provider's.
- **IX (nothing lost)**: a ride's track is kept with it, so an upload can be sent again.
- **X (checked, private)**: bounded inputs; the Strava tokens stay on the server; the
  privacy policy says what is kept, shown and sent.
- **XI (API promises)**: new endpoints and optional fields only. Exception: the voice chat's endpoints
  and fields left v1 with it at the maintainer's word (2026-10-28); the live site never switched it
  on, so no client could have relied on them.
- **XII (any screen)**: controls named in every language; the page's buttons and the profile's
  Strava controls and link measured at 44 px on a phone.
- **XIV (explain where met)**: the setup page says what connecting Strava does.

## Design

1. Rides, records, group races and presence: the author's patch, merged onto `main` and fixed in the
   review cycles the pull request lists.
2. Language: `?lang=` from the site's page; `t()` over the dictionary; data names `L({ru, kk, en})`.
3. Group link: `GET /groups/{id}`; `?group=` passed through the site's page; links lead to the site's
   page (`/me.page_url`), which hands out the CSRF cookie.
4. Strava: a `read,activity:write` grant in `StravaConnection`, refreshed tokens, a gzipped TCX from
   `RideTrack`, upload with `sport_type=VirtualRide`, status polled through the site.
5. Voice: taken out (the spec's User Story 6).
