---
name: data-validation
description: Checking and correcting the data already on the site - duplicate places, events without an exact start, dates and stages that differ from the organizer, names in three languages - and how the maintainer wants it done. Read before cleaning up events or locations, one by one or in bulk.
---

# Validating the site's data

Events arrive from the agents and by hand, and some arrive wrong. This is how what is already on the
site is checked and put right. Adding new events is `calendar-curation`; the rules of the place tree
are `locations`; reaching production is `production-access`.

## Ground rules

- **The organizer's own page is the truth.** When our date, place or list of stages differs from it,
  correct ours to the organizer's. When the organizer contradicts themselves (two start times on one
  page), transcribe both into the description and say so; never pick one.
- **Approved events are the maintainer's.** List what you would change and act after their go-ahead.
  A rule they state once ("trust the organizer's date") covers every event it fits: apply it, and
  name in the report each event it was applied to.
- **Check on live data right before acting.** The API read with the admin token sees every status
  and the deleted rows too. Dry-run anything that deletes, and keep a log of every request sent.
- **A bulk edit is tried on a copy first**: a local restore of the production backup
  (`production-access`), with the old text kept for rollback.
- **Runs of "?" in a description are the maintainer's notes** of what is still to clarify. Leave them.
- **A tentative event** the maintainer wants marked gets a first paragraph in all three languages:
  these are plans, not the final announcement; the announcement and the registration will appear on
  this page.

## Duplicate places

- **Find them**: siblings with similar names in any of the three languages; venues closer than about
  300 m; a venue without coordinates next to one with them. The usual pair: the one with coordinates
  is the real place, the other carries one event or none.
- **Look before deleting**: every event in the subtree, live and deleted, in every status --
  `GET /api/v1/competitions/?status=<s>&deleted=<b>&location_ids=<id>`.
- **Fix**: re-point the events onto the survivor, then delete the duplicate (`DELETE
  /api/v1/locations/<id>`, admin token; it refuses while a live event or child hangs off it). A
  rejected duplicate event goes first, by a soft delete.
- **A city or region whose only child is the hidden catch-all** cannot go through the API: the
  catch-all is a system fallback. Delete it in the production shell with treebeard's `.delete()`,
  after checking that its subtree holds no venue, no event (live or deleted), no news page and no
  member's saved preference -- move a member's preference onto the surviving node first. Dry run
  first. `tmp/dedup_c_prod_shell.py` (2026-10-30) is a worked example.
- **Look-alikes are not always duplicates**: a skating rink and a fountain 260 m apart are two
  meeting points; so are a race's start and its finish village.

## Events without an exact start

- **Which**: future approved events on a city's hidden "Other location", or with no location.
- **Where to look**: the organizer's event page, its regulations (often a PDF), the registration
  page, a "how to get there" page; an aggregator the organizer validated (Finishers) only as a
  fallback, and say so.
- **Coordinates**: the organizer's, else OpenStreetMap's for the place the organizer names (see
  `locations` for Nominatim). Search the tree for an existing venue first -- by name in all three
  languages and by distance.
- **Placing it**: the service account creates the venue under the event's city (approved, under an
  approved city) and re-points its own events; they stay approved. Someone else's approved event is
  re-pointed with the admin token.
- **When the organizer names only the town or village, keep the catch-all**: it already shows the
  town, and a venue at the town's centre would claim a precision nobody gave. An online event (a
  MyWhoosh or Zwift race) has no location.
- **Several starts for one event** (a trail festival with a start per distance) go into the
  description; do not invent a single venue.

## Dates and stages

- **The date lives in the event's fields.** A description that repeats it ("Date: 5 September",
  "on 23 May 2026") loses the repetition in all three languages; other dates -- race-pack pickup, a
  registration deadline -- stay.
- **A stage the organizer marks "???" or "not agreed"** is deleted. **An event deleted for a thin
  announcement** comes back only when the organizer's page holds a full one -- a place, a time and a
  way to register, not placeholder text.

## Names and languages

- **Each of ru, kk and en is its own language**: a Kazakh or English title that copies the Russian is
  translated.
- **Geography names match the place in all three languages** (a Turkish region named "Aksaray" in
  Russian carried "Ankara" in Kazakh and English). A spelling follows the place's own, as maps and
  the organizer write it (the village is "Shil'kovo").

## What is not added

- **Professional-only starts** -- UCI elite races, national-team selections -- as for the nightly
  agents.
- **Past events** (`calendar-curation`).

## Who approved what

An admin sees at the foot of an event's page who approved it and when; the API's event detail gives
admins `approved_by_id` and `approved_at`. Approvals older than the record show nothing.
