# cycling-site Constitution

cycling-site is a platform that helps people organize sport, and the activities around it, wherever
people move -- a race, a ride, a run, a hike, a walk. It announces an event, takes its registrations,
times it and publishes its results, with a knowledge base and news beside them. It is served at
universalbicycle.team in Russian, Kazakh and English.

It began as the calendar of a small cycling team in Almaty, Kazakhstan, and is meant for everyone:

- an organizer in Germany or Vietnam can announce their event here, open registration for it and
  time it;
- a rider in New York can open the map, see what is on in Almaty today -- a ride of three people as
  much as a championship -- and find where to go and when, in their own time and the event's.

The platform is open to everyone, after a check. Anyone may read what is public; a confirmed member
may propose an event, which waits for review; organizing -- registration on the site, events
published without waiting -- comes with the organizer role, which the owners grant on request. The
review and the role are deliberate: they keep the calendar free of spam and fake events, and are not
a barrier to remove.

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

### VI. Built for anyone, anywhere, in any activity where people move

The site starts as a small team's calendar in Almaty, Kazakhstan, but is built so that a person in
any country, organizing or joining any activity where people move -- on wheels, skis, skates or
foot, on road, trail, ice or water, timed or not -- finds it just as natural to use. Anything with a
start can be an event: a race, a ride of three friends, a walk, an evening on skates, once its event
type is in the calendar. Timing serves courses covered in laps and point-to-point courses from a
start to a finish. So the code assumes as little as it can about place and activity:

- Places, sports, disciplines, event types, time zones, map services and the like are data or
  configuration, not branches in the code. A new country, sport or activity should need a row or a
  setting, not a release. (Languages are the exception the maintainer chose -- principle IV.)
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

### X. Every input is checked, every member's data is private

Whatever reaches the site -- from a browser, the API, an agent or an uploaded file -- is checked
where it arrives, and the site shows nothing about a person that they did not choose to show.

- Rich text is sanitised on save; every string and list is bounded, and an over-long value is an
  error naming the field and its limit, not a server error.
- An uploaded HTML file is shown only in a sandboxed frame.
- A member's e-mail is never shown to other members, and signing up with a known address does not
  say that an account exists.
- Something a reader may not see answers as missing, never confirming that it exists: an event that
  is pending, hidden or invite-only and not theirs is a 404, and a wrong invitation key says nothing.
- Production tokens, keys and passwords live in the environment, never in the repository; the
  development settings' throwaway key is not one of them.

### XI. The API keeps its promises

Programs that talk to the site are not updated with it: a timing laptop at a race runs whatever
version was installed on it. So `/api/v1/` only grows.

- A change may add an endpoint or an optional field, and an answer may carry fields an older client
  ignores.
- Removing or renaming a field, making an optional one required or changing what a value means is a
  breaking change. It goes to a new version (`/api/v2/`), and v1 keeps serving until the maintainer
  retires it.
- An older client gets the answer it got before: finish-protocol generators that send only HTML
  keep publishing beside the ones that send the structured document (issue #310).

### XII. Usable by everyone, on any screen

Every page works on a phone as well as on a desktop, and with a keyboard or a screen reader as well
as with a mouse.

- Every control and every table header has an accessible name -- an icon button says what it does,
  a column is never drawn with an empty heading.
- Keyboard focus is visible, and everything a mouse can reach a keyboard can reach.
- A page fits a phone's width without scrolling sideways; a wide table scrolls inside its own box.
- The browser suite runs on phones as well as desktops (principle III), and its tests find controls
  by their role and name where they can, as a screen reader does -- so a control without a name
  fails its own test.

### XIII. Ask for a fact once, reuse it with permission

A participant, organizer, judge or any other person does not have to enter again a fact the
platform already knows and may use for that person and purpose. Forms and connected tools reuse
known values and offer editing, rather than asking people to bridge a gap between programs.

- Before adding an input, check profiles, registrations, event data and connected tools for its
  source. Carry stable references through imports and exports instead of asking for names or
  numbers again after losing the reference.
- Ask only for missing or changed facts. A recoverable error keeps the values already submitted;
  a conflict shows the existing facts and asks for the decision, not the whole form again.
- Reuse follows permissions and the person the fact concerns. Registering someone else does not
  make their identity the registering account's identity. Authentication and purpose-specific
  consent remain explicit; previous consent is not silently reused for a different purpose.

### XIV. Explain a requirement where the person meets it

A person can understand what a feature needs and what will happen before submitting data or
starting an operation. Necessary instructions are part of the feature, not knowledge they must
find in a ticket, source code or a conversation with the maintainer.

- Beside an input that depends on a service, file format or preparation step, show supported
  choices, accepted versions, an example and a reachable step-by-step guide. Distinguish what
  works now from what is planned; state required access and any known material limits or costs.
- Show progress, partial results and failures with their cause and the next available action.
  Unknown, unprocessed and unavailable are explicit states, never an unexplained empty result.
- Keep these explanations accessible on phones and by keyboard, in every site language. Generate
  changing lists and format versions from the same definitions the operation validates.

## Constraints

- Stack: Django 6 with Wagtail 7, PostgreSQL, Bootstrap 5.3 with the Bootswatch Lux theme,
  Python 3.13 (CI), dependencies locked with uv and exported to `requirements.txt`.
- Hosting: Render, behind Cloudflare. A change touching many rows is tried first on a production
  backup restored into a local scratch database.
- Scale: what the site can do is built for anyone, anywhere; how much it can carry is sized for its
  audience today, not for millions of users or requests per second. Load is worked on when growth
  calls for it. Until then no feature is shaped around a small or local audience (principle VI) --
  the limit is capacity, never what the site lets people do.
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

**Version**: 1.6.0 | **Ratified**: 2026-10-21 | **Last Amended**: 2026-10-25
