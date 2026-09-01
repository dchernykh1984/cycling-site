---
name: calendar-curation
description: Filling and cleaning the events calendar by hand - how the maintainer wants a sweep done, what an event body may say, and what to check before proposing anything. Read when adding or fixing events yourself rather than through an agent.
---

# Curating the calendar

Sometimes events are added or repaired by hand rather than by an agent: a source the agents do not
read, a correction, a backfill of past editions.

## How a sweep is run

- **Work in small batches**, a few sources at a time, and report after each. A long silent run that
  ends in a hundred events is not reviewable.
- **Analyse deeply, then propose.** Read the source's own pages rather than a listing row: the
  listing gives a name and a date, the event page gives the venue, the categories and the links.
- **Questions go into a file, not into the chat.** When a batch raises things only the maintainer
  can decide, write them in Russian to a file under `tmp/` and point at it, so they can answer at
  their own pace.
- **Past editions count.** Backfilling last year's races is wanted: they are the record somebody
  searching for results is looking for.

## What an event carries

- The body is a **short description**. The start point belongs to the location, the categories and
  the sport to their own fields. Do not write the coordinates into the text.
- **Every event has a depth-4 venue** (see `locations`). A ride announcement without an explicit
  place and time is not an event yet -- ask rather than guess a start point.
- **The announcement link opens that event's own page**, never the calendar, forum or channel it
  was found on.
- Markup: one `<p>` per paragraph. Stripping paragraphs and relying on `<br>` collapses the text
  into a wall, which is exactly what happened the last time it was done in bulk.
- Three locales, always.

## Before proposing

Check the site does not already have the event under another name or another spelling of the city,
and that the geography is not about to become a duplicate. After a bulk change, list what was
touched with links, so the maintainer can open them.

## Proposing through the API

The service account posts as an organizer, so its events arrive `pending_approval` and wait for a
human -- which is the point. An admin token would auto-approve; use the service account instead
unless told otherwise.
