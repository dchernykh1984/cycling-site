# Telegram agent

Reads the Telegram channels no other agent can -- private club channels and closed communities --
and proposes the events they announce (rides, hikes, runs, ski outings: the channels are outdoor
communities of every kind, not only cycling) as pending events on the site, in all three locales
(ru/kk/en), through the same API, dedup and location machinery as the events and Instagram agents.

## Why a member account and not a bot

The official way to automate Telegram is the Bot API, but a bot sees only chats an admin added it
to. These sources are other people's private channels and public *groups* (members, not
subscribers, and no `t.me/s/` web preview), readable only by a member. So this agent signs in as a
dedicated **service account** over MTProto (Telethon) -- Telegram's own open client protocol, with
credentials Telegram itself issues -- and reads as that member. This is the grey zone all userbots
live in: reading quietly is tolerated in practice, but the account can in principle be limited or
banned, which is why it must be a separate account nobody's personal history depends on.

The agent only ever **reads**. It never sends a message, never joins a channel, never accepts an
invite -- joining is done once, by hand, from the account's phone. Automatic joining is the exact
pattern Telegram's anti-spam exists to catch.

## Setting up the service account (once)

1. Get a SIM and register a fresh Telegram account on a phone. Virtual numbers tend to be banned
   on sight and refused API credentials -- use a real SIM.
2. On [my.telegram.org](https://my.telegram.org) (logged in as that account), open *API
   development tools* and create an application. This is free and instant, with no review; it
   yields `api_id` and `api_hash`.
3. From the account's phone, join every channel and group listed in `telegram_channels.yaml`.
4. Mint the session string locally (one login; the code arrives in the account's Telegram):

   ```bash
   pip install telethon
   python -c "
   from telethon.sessions import StringSession
   from telethon.sync import TelegramClient
   with TelegramClient(StringSession(), API_ID, 'API_HASH') as client:
       print(client.session.save())"
   ```

5. Store the three values as GitHub secrets: `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`,
   `TELEGRAM_SESSION`. The session string never goes into the repository. If Telegram ever
   revokes the session (a run will say so), mint a new one the same way and update the secret.

Until the secrets are set, a run reports that and exits cleanly -- private sources simply stay
unread, exactly as before this agent existed.

## What a run does

1. Reads `telegram_channels.yaml` (repo root) -- bare channel ids (`c/<id>`), public group
   handles (`@name`) and, as a last resort, invite links, each with an optional hint and home
   city. Ids and handles are domain-free on purpose: the agent reads over MTProto and does not
   care whether t.me resolves today.
2. Connects once with the stored session and reads **by time**: everything published in the last
   `TELEGRAM_RECENT_HOURS` (default **25** -- a nightly day plus an hour of overlap for a cron
   that fires late). Reading by time rather than by count is deliberate: measured on these
   channels, the newest 50 messages of a busy group do not reach back a single day while 50 of a
   quiet channel reach back two years. `TELEGRAM_MAX_POSTS` (default **1000**) is only a safety
   net against one runaway chat, and when it bites the run says so. Messages too short to be an
   announcement ("+", a thumbs-up) never reach the model. One connection, channels in sequence --
   a session hopping addresses inside one night is how sessions get revoked. A channel the account
   has not joined, an expired invite or a flood limit is reported per channel, never fatal.
3. Hands each channel's messages, **with their publication dates**, to the LLM (DeepSeek by
   default) and asks for the events being announced, in ru/kk/en. A channel with more than a
   hundred messages in the window becomes **several prompts**, not one huge one: a long context is
   not merely costlier, it is worse at finding the single announcement buried in a day of chatter.
4. Drops anything already known, previously rejected or already past; at most
   `TELEGRAM_MAX_EVENTS` (default **10**) per run and `TELEGRAM_MAX_PER_CHANNEL` (default **5**)
   from any one channel are proposed via `POST /api/v1/competitions/` (organizer token -> status
   `pending_approval`), placed on the location tree like every other agent's events.
5. `TELEGRAM_DRY_RUN=true` logs what would be proposed without posting anything.

To backfill after adding a channel, run it manually with a wider window -- e.g. `recent_hours=250`
for the last ten days, with `max_events` and `max_per_channel` raised to match, or the run will
cap itself long before it has read everything.

## Privacy

Two deliberate rules, because the sources are private:

- **Message text leaves Telegram**: it is sent to the LLM provider (DeepSeek) for extraction.
  Only channels whose announcements are meant to reach the people who would come -- riders,
  runners, hikers -- belong in the channels file.
- **Events are credited without disclosing a way in.** A public group is credited as
  "tg: @handle" -- searchable by anyone; a private channel by its display name alone, read from
  Telegram at fetch time. Never a t.me link, an invite or an id, and no `source_url`; a
  registration link survives only when the announcement itself gives an external one.

## Running it

Nightly by `.github/workflows/telegram-agent.yml` (a single job -- one session, one address), or
manually from the Actions tab (owner only), where dry run, the limits and the look-back window can
be set per run. Locally: export the env vars above plus `SITE_BASE_URL`, `AGENT_API_TOKEN`,
`LLM_API_KEY`, `LLM_BASE_URL` and run `python -m telegram_agent.run`.
