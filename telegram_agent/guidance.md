# Telegram agent guidance

Edit this file to steer what the Telegram agent proposes. It is re-read on every run and passed to
the model as instructions, so you can nudge it without changing code. You may write in Russian.

This agent is **not cycling-only**, deliberately. Its channels are local outdoor communities of
every kind -- cycling clubs, mountain-hiking groups, runners, skiers -- and the calendar carries
categories for all of them. Like the Instagram agent's guidance (and unlike the events agent's),
small community outings are welcome here: the Saturday ride, the Sunday hike, the "tomorrow at 7
from the usual place" message that never reaches any calendar.

## What to propose
- **Club rides and group rides with a fixed day and a meeting point** -- coffee rides, morning
  rides, a club's regular weekend outing.
- **Hikes, walks and ascents** -- походы, прогулки в горы, восхождения: a day hike to a lake, a
  multi-day trek, a summit walk. The mountain groups announce these constantly, and they are as
  much an event as any race.
- **Runs and ski outings** -- group runs, trail runs, ski races and ski trips.
- **Kids' starts and family events** -- balance-bike races, children's gran fondos, open days.
- **Amateur races and mass starts** a club or a shop organizes.
- **Federation events open to amateurs** -- an open mass start anyone can enter.
- An event counts even when it has no registration, no timing and no prizes. What it must have is
  a **day**, a **meeting place** and an invitation to come.

## What to skip
- **Anything that is not the sport itself.** This calendar carries activities people do under
  their own power. A drive out to Balkhash with tents, a carpool with the fuel split, a picnic,
  a party or a bus excursion is not an event here, however well it names a day and a time.
- **Private arrangements.** "Осталось одно место, подробности в личку" invites a person, not the
  public; the calendar publishes what anyone may come to.
- **Anything that already happened.** A chat is mostly photo reports and thanks after the outing
  -- "покатались", "сходили, спасибо всем". These are not events, whatever date they mention.
- **Talk about an announced event.** "Кто едет в субботу?", route bickering, a dozen replies --
  the announcement is one event; the conversation about it is none.
- **Questions and logistics chatter.** "Как добраться до космостанции?", "поделитесь контактами
  таксистов", "дорога открыта?" -- someone planning their own trip is not announcing one.
- **Results and standings.** Who won a finished start is reporting, not inviting.
- **Marketplace and gear talk**, sales, discounts, coach interviews, memes, stickers.
- **Closed sessions.** A team-only training that outsiders cannot join.
- **A message with no day at all**, or whose day is legible only on a poster image you cannot
  read. Do not invent a date -- skip the message instead.
- **Anything already on the site.** The prompt lists what the calendar holds.

## Recurring events
A community's weekly outing is a **new event each week**, not a duplicate of last week's. Only a
message about the outing on the **same day** as one already listed is a repeat. When a message
announces the next one without naming the date ("как обычно в субботу"), work the date out from
the day the message was published; if that is not possible, skip it rather than guessing.

## How to fill a proposal
- **All three locales (ru/kk/en)** for the title, the description and the venue name. Translate
  faithfully; if you genuinely cannot translate a field, repeat the Russian text there.
- **Title**: the event's own name as the community calls it, not a description of it.
- **Description**: simple HTML (`<p>`, `<br>`, `<ul>`/`<li>`, `<strong>`) with what a participant
  needs to show up: the gathering time and the start time, the meeting place, the route, the pace
  or difficulty, whether anyone may join, the fee, and how to register when the message says.
  Keep the community's own concrete wording; do not invent details the message does not state.
- **Type and discipline**: the lists cover more than cycling -- running, ski racing and hiking
  included. A hike or a walk goes to the hiking disciplines with the "Тренировка / Прогулка"
  type; a race goes to its discipline with the race type.
- **Never name the source yourself.** Do not name the channel, do not link it, and write no
  "source" line -- the credit is appended for you, in code: a public group as "tg: @handle", a
  private channel by its display name alone, never a link or an invite. A registration link is
  allowed only when the announcement itself gives an external one (a form, a race site) -- never
  a t.me link.
- **Country**: write the country's name the way people say it ("Казахстан", "Россия"), never a
  code like "KZ". The site matches geography by name, and a code leaves the event with no place.
- **Place**: the meeting point is the venue ("парковка Halyk Bank, Аль-Фараби 40"), with the city
  and its first-level region above it. When a message never says where -- because everyone in the
  chat knows -- use the city the maintainers gave the channel. Use the current official spelling
  ("Алматы", not "Алма-Ата"). Never write a placeholder like "Другая локация": leave the field
  empty instead, and repeat the start place in the Russian description so a reviewer can place it.

## Hints
- (add channel-specific hints in `telegram_channels.yaml` next to the channel they belong to)
