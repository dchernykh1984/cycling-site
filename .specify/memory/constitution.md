<!--
Sync Impact Report
- Version: none -> 1.0.0 (first constitution, issue #337); 1.0.0 -> 1.1.0: principle IV makes the
  three languages a deliberate choice; principle VI lets the maintainer accept a local assumption.
  1.1.0 -> 1.2.0: the light/dark screenshot comparison is retired (it guarded the skins refactoring,
  issue #324); principles II and III no longer name it.
  1.2.0 -> 1.3.0: principle IV requires localized reader-facing data fields by default, with
  an explicit exception for documents that belong to one locale.
  1.3.0 -> 1.4.0: principles added by the maintainer -- VII: what a participant or an organizer does
  with data on the site is also available through the API (the gaps are listed per area in
  specs/site/); VIII: one fact, one home; IX: nothing is lost by accident.
- Principles: I-V drawn from CLAUDE.md / AGENTS.md and the skills under .claude/skills and
  .agents/skills, which stay the detailed runtime guidance; VI-IX set by the maintainer (no local or
  sport-specific hardcoding; an API by default; one fact, one home; nothing is lost by accident).
- Templates: plan-template.md's "Constitution Check" gate reads these principles; no template
  needed changes.
-->

# cycling-site Constitution

cycling-site is a calendar of timed-sport events -- races, rides, runs and their kin -- with a
knowledge base, news, race registration, refereeing and live protocols, served at
universalbicycle.team in Russian, Kazakh and English. It began with events in Kazakhstan,
Kyrgyzstan and Russia; it is meant for everyone.

## Core Principles

### I. Facts come from their source

Announcements, articles and event data carry only what their source says. When a source is
contradictory, it is transcribed and the contradiction named, never tidied into a guess.
Coordinates and venues are looked up, never recalled from memory. A specification describes the
behaviour the code and its tests show; where that is unknown, it says so (`NEEDS CLARIFICATION`)
rather than inventing it.

### II. Some decisions belong to the maintainer

A pull request is merged by the maintainer, or by an agent only when the maintainer asks for it in
the message being answered.
Approved events are theirs: changing one -- its links, location or dates -- needs their explicit
go-ahead. The events agents spend money on every run and are started only on request. The light
and dark themes are kept as they are unless the maintainer asks for a change.

### III. Every change carries its tests (NON-NEGOTIABLE)

A behaviour change ships with the tests that pin it: a Django unit test for backend behaviour, a
Playwright test under `tests/e2e/` for anything a person sees in a browser. A bug fix gets a
regression test that fails without the fix. Tests are named after the behaviour, not the function.
Coverage stays at 90% or above, and every check of the pipeline -- unit tests, pre-commit, the
browser suite on five browsers and devices and once per skin, the dependency audit -- is green
before work is reported done.

### IV. The reader's language, in the address

Everything a reader sees exists in every language the site offers: Russian for its audience,
English for everyone else, Kazakh out of respect for Kazakhstan. The three are a deliberate choice
and a fourth is not planned -- it would mean translating every event and article -- so code may
name the three where that is simpler. Every reader-facing URL carries its language prefix (`/ru/`,
`/kk/`, `/en/`); machine-facing ones (`/api/v1/`, admin, media, sitemap, robots) do not. Source
files are ASCII and UTF-8; text in the site's languages lives in the translation catalogues and in
the agents' guidance files.

Reader-facing names, titles, captions and descriptions have separate values for ru, kk and en
by default, including the forms and administration tools that edit them. Existing text is kept
when translations are introduced. A document such as a knowledge article may instead belong to
one locale and appear only in that locale's listings. IDs, dates, numbers and URLs are not
translated. Each area records any other exception in its specification.

### V. Small, complete, reviewable changes

Each atomic change is one commit with a one-line message in the commitizen types, never
mentioning the assistant that wrote it. Work is reviewed in cycles -- three by default -- each
finding fixed in a commit of its own. Pull requests are merged by rebase so every commit survives
on a linear history. A change finishes every part it touches -- callers, tests, translations,
setup hints, documentation, specifications -- and adds nothing nobody asked for.

### VI. Built for anyone, anywhere, in any timed sport

The site starts as a small team's calendar in Almaty, Kazakhstan, but is built so that a person in
any country, following any sport where time is kept -- on wheels, skis, skates or foot, on road,
trail or water -- finds it just as natural to use. So the code assumes as little as it can about
place and sport:

- Places, sports, disciplines, event types, time zones, map services and the like are data or
  configuration, not branches in the code. A new country or sport should need a row or a setting,
  not a release. (Languages are the exception the maintainer chose -- principle IV.)
- Nothing local is written into the code as a default the rest of the world must live with -- not a
  city, a country, a currency, a time zone, a provider or a unit. Where a local choice is needed
  today, it sits in one named setting and the specification records it.
- Examples in issues, specifications and conversations (a sport, a city, a race) explain the idea;
  they are not values to copy into the code.
- Where the code still assumes a place or a sport, the area's file in `specs/site/` lists it under
  "Local assumptions", and a change touching that code removes the assumption rather than adding
  another -- unless the maintainer marked it **Accepted**.

### VII. What a member does on the site, a program can do through the API

What a participant or an organizer reads or changes on the site -- events, entries, results,
comments, their own profile -- is also available through the API (`/api/v1/`), so the timing
tools, the events agents and a member's own programs work with the same data a person does.

- A feature that lets a participant or an organizer read or change data ships its API operations
  in the same change, with their tests (principle III).
- The API keeps the site's rules: who may see, create, change or delete something is decided the
  same way on both, and what the site shows per language the API reads and writes per language
  (principle IV).
- Work only admins and owners do -- moderating geography and submissions, the gallery, the site's
  own texts -- may have an API but need not.
- A member action is left out of the API only for a reason, recorded in the area's specification:
  signing up and signing in, for example, establish who an API caller is, so they come before the
  API rather than through it.
- Where a member action still has no API, the area's file in `specs/site/` lists it under "API
  gaps". A change that reworks an action listed there closes its gap rather than leaving it open --
  unless the maintainer marked it **Exception**.

### VIII. One fact, one home

A fact is stored in one place and everything else derives it from there: an event's time zone is
worked out from its place on every use rather than saved beside it (issue #344). A rule is written
once and shared -- the server hands the browser what it needs, as the protocol search receives the
server's table for folding one script into another, rather than the rule being written again in
JavaScript.

- Before adding a model, a field, a setting or a helper, look for the one that already holds it.
- A duplicate -- a second venue for the same place, a second copy of a list -- is merged, not kept
  alongside; a merge that touches an approved event waits for the maintainer (principle II).
- Where a copy cannot be avoided -- a cache, a column kept for speed -- one side is the source, the
  other is rebuilt from it, and the code says which.

### IX. Nothing is lost by accident

What people entered or uploaded survives every change to the site.

- Events, articles, places and registration categories are soft-deleted: deleting one hides its
  row rather than erasing it. What is erased outright -- a comment, a cancelled entry, a gallery
  photo -- is erased by a rule its area's specification states.
- A migration carries existing data across; one that rewrites many rows is tried first on a
  production backup restored locally (see Constraints).
- A new form of data keeps the old one working: localized fields keep the existing text
  (principle IV); the structured protocol document arrived beside the HTML, and old HTML protocols
  and generators that send only HTML still work (issue #310).
- Old versions are dropped only by a written rule too: a protocol keeps its ten most recent.
- A file is removed only after the database change that freed it is committed, so a failed write
  never leaves a row pointing at a missing file.

## Constraints

- Stack: Django 6 with Wagtail 7, PostgreSQL, Bootstrap 5.3 with the Bootswatch Lux theme,
  Python 3.13 (CI), dependencies locked with uv and exported to `requirements.txt`.
- Hosting: Render, behind Cloudflare. A change touching many rows is tried first on a production
  backup restored into a local scratch database.
- The look of the site is split into skins (`skins/`): designers own their skins; a change to the
  site that breaks a skin does not merge until the skin is green again.

## Development Workflow

- A feature with its own GitHub issue gets a specification in `specs/<issue>-<short-name>/`
  (`spec.md`, then `plan.md` and `tasks.md`), made with the Spec Kit skills (`/speckit-specify`,
  `/speckit-clarify`, `/speckit-plan`, `/speckit-tasks`, `/speckit-analyze`, `/speckit-implement`).
  The maintainer reviews the specification and the plan before implementation starts.
- `specs/site/` describes the site as it works today, one file per area. A change that alters an
  area's behaviour updates its file in the same pull request.
- A bug fix or a small change needs no specification of its own, but still updates `specs/site/`
  when it changes described behaviour.

## Governance

This constitution states the principles; `CLAUDE.md`, `AGENTS.md` and the skills they list hold
the detail and are kept consistent with it. The maintainer amends it through a pull request that
bumps the version -- MAJOR for a principle removed or redefined, MINOR for one added or materially
expanded, PATCH for wording -- and updates the Last Amended date. Plans check themselves against
it in their "Constitution Check".

**Version**: 1.4.0 | **Ratified**: 2026-10-21 | **Last Amended**: 2026-10-24
