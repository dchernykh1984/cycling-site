---
name: events-agents
description: The three import agents that find events and propose them to the site - what each reads, when they run, how to read their logs, and the rule about never starting one uninvited.
---

# The import agents

Three separate jobs, one shared pipeline (`agent/pipeline.py`), all posting through the site API as
a service account. Everything they propose lands as `pending_approval` for a human.

| Agent | Reads | Schedule (UTC) |
| --- | --- | --- |
| `agent/` (events) | web calendars, organizer sites, public Telegram feeds via `t.me/s/` | 22:17 daily |
| `instagram_agent/` | club accounts listed in `instagram_accounts.yaml` | 23:17 daily |
| `telegram_agent/` | private channels and member-only groups, over MTProto | 00:17 daily |

**Never start one without being asked.** Each run spends money at the LLM provider. When the
maintainer does ask: `gh workflow run agent.yml --ref main -f dry_run=false -f max_events=25`.

## Sources

`events_sources.yaml` groups sources by kind -- `aggregators`, `organizers`, `telegram_public` --
and each entry may carry a free-text `hint` passed to the model. That hint is the cheapest fix
available when a source is being read badly: it can name where the race pages live, what to ignore,
which link to take.

`telegram_channels.yaml` and `instagram_accounts.yaml` do the same for the other two.

## Reading a run

`gh run list --workflow agent.yml` then `gh run view <id> --log`. The summary at the end names every
proposed event with its link and place, every skipped candidate with the reason, and per-source
counts (`= <source>: N extracted, M proposed`). "0 extracted" and "the source was barely read" look
identical in the count alone -- the per-source lines are what tell them apart.

A schedule fires late. GitHub queues cron runs best-effort: 20 to 60 minutes of drift is normal, and
during Actions incidents it stretches to hours or the run is skipped entirely.

## Links

An event's announcement link must open **that event**, never the page it was found on. A forum
index, a channel feed and a calendar front page announce nothing in particular:
`links.announces_one_event()` rejects them, and `links.link_for_title()` recovers the right one by
matching the event's name against every link the page carried.

For Telegram, the address of the post itself is the link: `t.me/<handle>/<id>` for a public channel,
`t.me/c/<internal-id>/<message>` for a private one, with the forum topic in between where there is
one. The model names the message; the address is built in code, never copied from the model.

## Duplicates and deletions

The pipeline compares a candidate against everything the site knows, including deleted events: a
**soft-deleted** event is blocked from being proposed again. So when the point is to have an agent
re-propose something (after fixing a bug, say), the old row has to be **hard-deleted**.
