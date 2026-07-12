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
- Events that already happened.
- Anything you are not confident is a real event with a concrete date.

## How to fill a proposal
- **Announcement link (`source_url`):** if you found the event on an aggregator / calendar
  (integrator), link to the announcement on the **organizer's own site** -- aggregators usually
  copy events from there -- not the aggregator page.
- **Location:** state the event's city in the (Russian) description. If you cannot determine the
  exact city, name the **nearest** one and add a note in Russian for the reviewer, e.g.
  "Указан ближайший город -- просьба к ревьюеру уточнить локацию и навести порядок."

## Hints
- (add source-specific hints here, e.g. "on granfondo.com.kz the schedule is under /ru/calendar")
