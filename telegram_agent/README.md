# Telegram agent

Reads the Telegram channels no other agent can -- private club channels and closed communities --
and proposes the rides they announce as pending events on the site, in all three locales
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

1. Reads `telegram_channels.yaml` (repo root) -- invite links (`t.me/+...`), internal links
   (`t.me/c/<id>`) and public group handles, each with an optional hint and home city.
2. Connects once with the stored session and reads each channel's newest
   `TELEGRAM_MAX_POSTS` (default **10**) messages, keeping those from the last
   `TELEGRAM_RECENT_DAYS` (default **21**) days. One connection, channels in sequence -- a
   session hopping addresses inside one night is how sessions get revoked. A channel the account
   has not joined, an expired invite or a flood limit is reported per channel, never fatal.
3. Hands each channel's messages, **with their publication dates**, to the LLM (DeepSeek by
   default) and asks for the rides being announced, in ru/kk/en.
4. Drops anything already known, previously rejected or already past; at most
   `TELEGRAM_MAX_EVENTS` (default **10**) per run and 5 per channel are proposed via
   `POST /api/v1/competitions/` (organizer token -> status `pending_approval`), placed on the
   location tree like every other agent's events.
5. `TELEGRAM_DRY_RUN=true` logs what would be proposed without posting anything.

## Privacy

Two deliberate rules, because the sources are private:

- **Message text leaves Telegram**: it is sent to the LLM provider (DeepSeek) for extraction.
  Only channels whose announcements are meant to reach riders belong in the channels file.
- **Events carry no attribution at all.** No channel name, no t.me link, no "source" line, no
  `source_url`; a registration link survives only when the announcement itself gives an external
  one. Someone reading the site cannot tell which channel an event was read in.

## Running it

Nightly by `.github/workflows/telegram-agent.yml` (a single job -- one session, one address), or
manually from the Actions tab (owner only), where dry run, the limits and the look-back window can
be set per run. Locally: export the env vars above plus `SITE_BASE_URL`, `AGENT_API_TOKEN`,
`LLM_API_KEY`, `LLM_BASE_URL` and run `python -m telegram_agent.run`.
