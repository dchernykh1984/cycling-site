# Telegram agent guidance

Edit this file to steer what the Telegram agent proposes. It is re-read on every run and passed to
the model as instructions, so you can nudge it without changing code. You may write in Russian.

Like the Instagram agent's guidance -- and unlike the events agent's -- club rides are welcome
here. These channels are where a club talks to its own members: the Saturday ride, the kids'
start, the "tomorrow at 7 from the usual place" message that never reaches any calendar.

## What to propose
- **Club rides and group rides with a fixed day and a meeting point** -- coffee rides, morning
  rides, a club's regular weekend outing.
- **Kids' starts and family events** -- balance-bike races, children's gran fondos, open days.
- **Amateur races and mass starts** a club or a shop organizes.
- **Federation events open to amateurs** -- an open mass start anyone can enter.
- A ride counts even when it has no registration, no timing and no prizes. What it must have is a
  **day**, a **meeting place** and an invitation to come.

## What to skip
- **Anything that already happened.** A chat is mostly photo reports and thanks after the ride --
  "покатались", "спасибо всем, кто приехал". These are not events, whatever date they mention.
- **Talk about an announced ride.** "Кто едет в субботу?", route bickering, a dozen replies -- the
  announcement is one event; the conversation about it is none.
- **Results and standings.** Who won a finished start is reporting, not inviting.
- **Training and marketing posts**, discounts, coach interviews, memes, stickers.
- **Closed sessions.** A team-only training that outsiders cannot join.
- **A message with no day at all**, or whose day is legible only on a poster image you cannot
  read. Do not invent a date -- skip the message instead.
- **Anything already on the site.** The prompt lists what the calendar holds.

## Recurring rides
A club's weekly ride is a **new event each week**, not a duplicate of last week's. Only a message
about the ride on the **same day** as one already listed is a repeat. When a message announces the
next ride without naming the date ("как обычно в субботу"), work the date out from the day the
message was published; if that is not possible, skip it rather than guessing.

## How to fill a proposal
- **All three locales (ru/kk/en)** for the title, the description and the venue name. Translate
  faithfully; if you genuinely cannot translate a field, repeat the Russian text there.
- **Title**: the ride's own name as the community calls it, not a description of it.
- **Description**: simple HTML (`<p>`, `<br>`, `<ul>`/`<li>`, `<strong>`) with what a rider needs
  to show up: the gathering time and the start time, the meeting place, the route, the pace,
  whether anyone may join, the fee, and how to register when the message says. Keep the
  community's own concrete wording; do not invent details the message does not state.
- **Never name the source.** These are private channels and closed communities: do not name the
  channel, do not link it, do not mention Telegram, and write no "source" line -- the event
  carries no attribution at all, by design. A registration link is allowed only when the
  announcement itself gives an external one (a form, a race site) -- never a t.me link.
- **Place**: the meeting point is the venue ("парковка Halyk Bank, Аль-Фараби 40"), with the city
  and its first-level region above it. When a message never says where -- because everyone in the
  chat knows -- use the city the maintainers gave the channel. Use the current official spelling
  ("Алматы", not "Алма-Ата"). Never write a placeholder like "Другая локация": leave the field
  empty instead, and repeat the start place in the Russian description so a reviewer can place it.

## Hints
- (add channel-specific hints in `telegram_channels.yaml` next to the channel they belong to)
