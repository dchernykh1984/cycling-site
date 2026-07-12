# Agent guidance

Edit this file to steer what the events agent proposes. It is re-read on every run and passed to
the model as instructions, so you can nudge it (e.g. "look at the calendar page of site X",
"include gravel races", "ignore training sessions") without changing code.

## What to propose
- Real, **upcoming** cycling competitions (road, MTB, gravel, cyclocross, gran fondo, etc.).
- Prefer events in Kazakhstan, Kyrgyzstan and nearby regions.

## What to skip
- Training rides, club meetups and social rides without a fixed race date.
- Events that already happened.
- Anything you are not confident is a real event with a concrete date.

## Hints
- (add source-specific hints here, e.g. "on granfondo.com.kz the schedule is under /ru/calendar")
