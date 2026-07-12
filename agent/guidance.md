# Agent guidance

Edit this file to steer what the events agent proposes. It is re-read on every run and passed to
the model as instructions, so you can nudge it (e.g. "look at the calendar page of site X",
"include gravel races") without changing code. You may write in Russian.

## Priority
- **Kazakhstan and Kyrgyzstan events come first.** Other regions (Russia, etc.) are lower priority
  -- propose them only after the KZ/KG ones.

## What to propose
- Real, **upcoming** cycling competitions (road, MTB, gravel, cyclocross, gran fondo, etc.).

## What to skip
- Training rides, club meetups and social rides without a fixed race date.
- **Official / elite federation races** (Kazakhstan or Kyrgyzstan cycling federation championships)
  -- UNLESS the announcement explicitly says it is for **masters / amateurs (любительские заезды)**.
  Elite federation races are not of interest to us.
- **Do NOT add past events** -- only upcoming ones, never events that already happened.
- Non-cycling posts, chat replies, group rules ("Правила группы") and vague personal chatter
  (e.g. "завтра в 5:00 стартуем из-под дуба") -- only real announcements with a place and a date.
- Anything you are not confident is a real event with a concrete date.

## How to fill a proposal
- **Announcement link (`source_url`):** link to the announcement on the **organizer's own site**,
  and prefer the **specific race/event page**, not the organizer's homepage. If you found the event
  on an aggregator / calendar (integrator), still link to the organizer's page -- aggregators
  usually copy events from there -- not the aggregator.
- **Location -- prefer concrete places.** The site's locations are a tree: country -> region ->
  city -> specific venue (the start point). Try hard to find the **real** country, region, city and
  the **specific start venue / address** of the event, and put them in the (Russian) description.
  Prefer concrete values over generic ones: do NOT settle for the placeholders "Другая страна" /
  "Другой регион" / "Другой город" / "Другая локация" -- find the actual place whenever the
  announcement gives it; use a generic placeholder only as a last resort, when there is genuinely
  no more specific information.
  If the event is in a city the site does not have yet, do not force a wrong one: name the real
  city/start in the description and ask the reviewer (in Russian) to add the location, e.g.
  "Город/старт: <город/место>. Просьба к ревьюеру завести локацию и уточнить точку старта."

## Hints
- (add source-specific hints here, e.g. "on granfondo.com.kz the schedule is under /ru/calendar")
