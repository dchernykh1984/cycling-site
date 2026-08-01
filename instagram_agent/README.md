# Instagram agent

A scheduled tool that reads the Instagram accounts of local clubs and federations and proposes the
rides they **announce** as **pending** competitions for a human moderator to approve.

It exists because half of what happens on a bike here never reaches a website: the Saturday coffee
ride, a kids' start, a club's open day are posted to followers and nowhere else. The events agent
(`agent/`) reads websites and calendars; this one reads feeds. They are separate agents on separate
schedules, but they share what must not diverge -- the events the site already knows, the duplicate
detection those feed, the location tree, and the API they post through.

## How it works (one run)
1. Reads `instagram_accounts.yaml` (repo root) and `instagram_agent/guidance.md`, both re-read
   every run.
2. Asks the site API for what it already knows: approved, its own pending, anything deleted, and
   its own rejected events with reasons.
3. Reads each account's recent posts, one account at a time with a pause between them. Only what a
   logged-out browser is served, one request per account. Accounts that cannot be read -- private,
   personal (not Business/Creator), renamed -- are reported with the reason rather than retried.
4. An LLM (DeepSeek by default) is given each post **with the date it was published** and its
   permalink, and asked for the rides being announced.
5. Drops anything already known, previously rejected or already past, and proposes at most
   `INSTAGRAM_MAX_EVENTS` (default **10**) via `POST /api/v1/competitions/` (organizer token ->
   status `pending_approval`), placing each event on the location tree like the events agent does.

The agent is **stateless**: the site itself is its memory.

## What it takes and what it leaves

A club's feed is mostly not events. The prompt's first rule is that a photo report of a ride that
already happened, a training post, a results table of a finished championship, an advertisement or a
motivational text are **not** events. An event is a post inviting people to something that has not
happened yet.

The second rule is about dates. Rides are announced as "this Saturday, 1 August", which is only a
date if you know the day the post was published -- so every post carries its publication date, and
resolving a relative date against it is explicitly not counted as guessing. A post whose day is
legible only on a poster image is skipped rather than dated by invention.

## Accounts (`instagram_accounts.yaml`)
Beside `events_sources.yaml` at the repo root. Each entry is a bare username, an `@handle` or a
pasted profile link, or a mapping with:
- `hint` - a free-text nudge for the model (what this account posts, and what it does not).
- `city` - where this club rides, used when a post never names the place because its followers
  already know it.
- `enabled: false` - pause an account without losing it.

Only **professional** (Business/Creator) accounts can be read; a personal account answers with
nothing useful. An account that only publishes results and photo reports costs a request every night
and yields nothing -- it does not belong here.

## Guidance

`instagram_agent/guidance.md` steers what a run proposes and is re-read every run, so it can be
edited without touching code. It is deliberately **not** the events agent's guidance: that file
tells the model to skip club rides and social rides, which are exactly what this agent is for.

## Guardrails
- `INSTAGRAM_MAX_EVENTS` (default **10**) caps what one run proposes.
- `INSTAGRAM_MAX_POSTS` (default **10**) caps how many of an account's newest posts are read.
  Raising it has a ceiling: the profile reply carries about a dozen posts and this reader does not
  page further back on purpose.
- `INSTAGRAM_RECENT_DAYS` (default **21**) is how far back a run looks.
- Dedup against everything the site knows, shared with the events agent, so the two cannot propose
  each other's events. A club's weekly ride is a new event each week; only one on the same day as a
  known event is a repeat.
- `INSTAGRAM_DRY_RUN=true` (or the workflow's `dry_run` input) logs the events without posting.
- A human moderator approves everything - nothing goes public automatically.

## Running locally
```
SITE_BASE_URL=https://universalbicycle.team \
AGENT_API_TOKEN=... LLM_API_KEY=... LLM_BASE_URL=https://api.deepseek.com \
LLM_MODEL=deepseek-v4-flash INSTAGRAM_MAX_EVENTS=10 INSTAGRAM_DRY_RUN=true \
python -m instagram_agent.run
```
(only `pyyaml` is needed beyond the standard library)

## Secrets
The same ones the events agent uses -- `AGENT_API_TOKEN`, `LLM_API_KEY`, `LLM_BASE_URL`,
`LLM_MODEL`, `SITE_BASE_URL`. It posts as the same organizer account.

Runs daily at **23:17 UTC (04:17 Almaty)**, an hour after the events agent so the two never overlap
and this one sees what that one just proposed, and outside the hours where the model bills double.
On demand via the **Run workflow** button (owner only).

## Reading Instagram

This reads the profile endpoint Instagram's own web client calls, without logging in. The official
route is the Graph API's `business_discovery`, which returns the same captions, dates and images for
professional accounts; it needs a Meta app with business verification and App Review. `fetch.py` is
the only module that talks to Instagram, so swapping in that backend touches nothing else.
