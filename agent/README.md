# Events agent

A scheduled tool that discovers cycling events from a curated source list and proposes them to the
site as **pending** competitions for a human moderator to approve. It is one of several ways events
get added - the normal GUI/API flows for real users are unchanged.

## How it works (one run)
1. Reads `events_sources.txt` (repo root, re-read every run) and `agent/guidance.md`.
2. Asks the site API for what it already knows: approved + its own pending (to avoid duplicates)
   and its own **rejected** events with reasons (to avoid re-proposing similar ones). Both lists,
   plus events accepted earlier in the same run, are shown to the LLM so it can skip near-duplicates
   that the exact-match dedup would miss.
3. Fetches each source - websites and **public** Telegram channels via the `t.me/s/<channel>`
   web preview. Private Telegram (`t.me/+invite`, `t.me/c/...`) is skipped and logged for now.
4. An LLM (DeepSeek by default, any OpenAI-compatible endpoint) extracts event candidates.
5. Drops anything already known or previously rejected, keeps only valid future events, and
   proposes at most `MAX_EVENTS_PER_RUN` (default **10**) via `POST /api/v1/competitions/`
   (organizer token -> status `pending_approval`).
6. **Second pass (enrichment):** before posting, for each accepted event that links to its own
   specific web page, the agent fetches that page and asks the LLM to refine the event (formatted
   description, exact date, route/registration links, location). Any failure falls back to the
   first-pass data. Toggle with `AGENT_ENRICH_DETAILS` (default on). It cannot run JavaScript, so
   JS-only pages add little.

The agent is **stateless**: the site itself is its memory (it re-derives "already there" and
"rejected, don't repeat" from the API each run).

## Guardrails
- Hard cap of `MAX_EVENTS_PER_RUN` proposals per run (agent-side; the site does not limit users).
- Dedup against existing + past rejections: exact (title+date) plus fuzzy, so a near-duplicate of
  an existing event -- same words, close date, worded differently, or in **another language** (the
  ru/kk/en titles are compared per-locale) -- is dropped too.
- `AGENT_DRY_RUN=true` (or the workflow's `dry_run` input) logs candidates without posting.
- A human moderator approves everything - nothing goes public automatically.

## Running locally
```
SITE_BASE_URL=https://universalbicycle.team \
AGENT_API_TOKEN=... LLM_API_KEY=... LLM_BASE_URL=https://api.deepseek.com \
LLM_MODEL=deepseek-chat MAX_EVENTS_PER_RUN=10 AGENT_DRY_RUN=true \
AGENT_ENRICH_DETAILS=true \
python -m agent.run
```
(only `beautifulsoup4` is needed beyond the standard library)

## Secrets / variables (GitHub -> Settings -> Secrets and variables -> Actions)
- `AGENT_API_TOKEN` (secret) - API token of a dedicated **organizer** account (the "bot").
- `LLM_API_KEY` (secret) - DeepSeek (or other) API key.
- `LLM_BASE_URL` (secret) - e.g. `https://api.deepseek.com`.
- `LLM_MODEL` (secret, optional) - e.g. `deepseek-chat` (defaults to `deepseek-chat` if unset).
- `SITE_BASE_URL` (secret, optional) - the site to post to, e.g. `https://universalbicycle.team`
  (defaults to the production URL if unset).

Runs daily at **00:43 UTC (05:43 Almaty)**, and on demand via the **Run workflow** button (owner
only). Scheduled runs only fire from the default branch (`main`).
