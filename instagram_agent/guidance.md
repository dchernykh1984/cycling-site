# Instagram agent guidance

Edit this file to steer what the Instagram agent proposes. It is re-read on every run and passed to
the model as instructions, so you can nudge it without changing code. You may write in Russian.

This is **not** the events agent's guidance, and the difference is deliberate. That agent reads
calendars and organizer sites, where everything is a competition, and it is told to skip club rides
and social rides. This one exists precisely because those rides are announced nowhere else -- a
club's Saturday coffee ride never appears on a calendar, and it is half of what actually happens on
a bike here. Applying the other file's rules here would make every run propose nothing.

## What to propose
- **Club rides and group rides with a fixed day and a meeting point** -- coffee rides, morning
  rides, "early bird" rides, a club's regular Saturday outing. These are the point of this agent.
- **Kids' starts and family events** -- balance-bike races, children's gran fondos, open days.
- **Amateur races and mass starts** a club or a shop organizes.
- **Federation events open to amateurs** -- an open mass start anyone can enter.
- A ride counts even when it has no registration, no timing and no prizes. What it must have is a
  **day**, a **meeting place** and an invitation to come.

## What to skip
- **Anything that already happened.** A club's feed is mostly photo reports of the last ride --
  "покатались", "спасибо всем, кто приехал", "коферайд удался", a gallery from the weekend. These
  are not events, whatever date they mention.
- **Results and standings.** A federation posting who won a championship is reporting, not inviting.
- **Training and marketing posts** -- why a balance bike is good for a child, a coach interview, a
  discount, a motivational text, a meme.
- **Closed sessions.** A team-only training that outsiders cannot join.
- **A post with no day at all**, or whose day is legible only on a poster image you cannot read.
  Do not invent a date -- skip the post instead.
- **Anything already on the site.** The prompt lists what the calendar holds.

## Recurring rides
A club's weekly ride is a **new event each week**, not a duplicate of last week's. Only a post about
the ride on the **same day** as one already listed is a repeat. When a post announces the next ride
without naming the date ("as usual on Saturday"), work the date out from the day the post was
published; if that is not possible, skip it rather than guessing.

## How to fill a proposal
- **All three locales (ru/kk/en)** for the title, the description and the venue name. Translate
  faithfully; if you genuinely cannot translate a field, repeat the Russian text there.
- **Title**: the ride's own name as the club calls it -- "Early Bird Coffee Ride: UBT Giant x
  Medeo", "Гранд-фондо на беговелах" -- not a description of it.
- **Description**: simple HTML (`<p>`, `<br>`, `<ul>`/`<li>`, `<strong>`) with what a rider needs to
  show up: the gathering time and the start time, the meeting place, the route, the pace, whether
  anyone may join, the fee, and how to register when the post says. Keep the club's own concrete
  wording; do not invent details the post does not state.
- **Link**: `source_url` is the permalink of the post the event came from, exactly as given above
  that post. A registration link goes in `url_registration` only if the post carries one.
- **Place**: the meeting point is the venue ("магазин Giant, Абая 47"), with the city and its
  first-level region above it. When a post never says where -- because everyone following the club
  knows -- use the city the maintainers gave the account. Use the current official spelling
  ("Алматы", not "Алма-Ата"). Never write a placeholder like "Другая локация": leave the field
  empty instead, and repeat the start place in the Russian description so a reviewer can place it.

## Hints
- (add account-specific hints in `instagram_accounts.yaml` next to the account they belong to)
