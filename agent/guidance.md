# Agent guidance

Edit this file to steer what the events agent proposes. It is re-read on every run and passed to
the model as instructions, so you can nudge it (e.g. "look at the calendar page of site X",
"include gravel races") without changing code. You may write in Russian.

## Priority
Two ladders. Work down the geography first, and inside each step prefer cycling.

- **By geography:** Kazakhstan (Almaty above all) -> Kyrgyzstan -> Russia and China -> the rest of
  the world. A start from a lower step is still worth proposing -- it just waits until the closer
  ones are done.
- **By sport:** cycling first; then running, triathlon and cross-country skiing.

## What to propose
- Real, **upcoming** competitions:
  - **cycling** -- road, MTB, gravel, cyclocross, gran fondo, brevets, bikepacking, etc.;
  - **running** -- marathons, half marathons, trail and mountain running, ultras;
  - **triathlon** and its relatives (duathlon, aquathlon, swimrun);
  - **cross-country skiing** -- races and ski marathons.
  Anywhere in the world: the site filters events by country, so a good race far away is still
  worth having. Just respect the two ladders above when the run's budget is limited.

## What to skip
- **Training rides, club rides, group rides and "дальняки" (long social rides)** -- even when they
  have a fixed date and a GPX / Strava track. Tell-tale signs: a gathering "for coffee", coffee /
  food stops along the route, a target pace or power (e.g. "2.0 W/kg в гору") instead of a
  competitive format, a club posting its own regular ride, and no registration, timing, categories,
  results or prizes. The calendar is for **competitions** (racing with results / standings), not
  group rides. When a post looks like a social ride, skip it.
- **Official / elite federation races** (a national federation's championships, in cycling or in any
  other sport, including youth and junior ones) -- UNLESS the announcement explicitly says it is for
  **masters / amateurs (любительские заезды)**. Elite federation races are not of interest to us.
- **Do NOT add past events** -- only upcoming ones, never events that already happened.
- Off-topic posts, chat replies, group rules ("Правила группы") and vague personal chatter
  (e.g. "завтра в 5:00 стартуем из-под дуба") -- only real announcements with a place and a date.
- Anything you are not confident is a real event with a concrete date.
- **No confirmed city / only a draft page.** If the announcement does not name the city or place
  where the event is held, or the organizer's page is just a draft/placeholder without real details,
  skip it -- do not add it to the calendar.
- **Date shown only in an image.** If the start date is only on a poster/picture (not as text you
  can read), do NOT guess it -- skip the event rather than invent a date.

## Avoid duplicates
- **Never propose an event that is already on the site.** The prompt lists the events the site
  already has (and the ones you proposed earlier in this same run). Skip an event when it is the
  **same race** -- same series / organizer, around the same date and city -- even if its title is
  worded differently, in another language, or with/without the year. When unsure, skip it. The
  existing list may show an event in a **different language** than the announcement (e.g. it is
  stored in English while the post is in Russian) -- match by meaning, city and date, not exact words.
- **The same event often appears in several sources** (the organizer's site, an aggregator, a
  Telegram post). Propose each real event **once**.
- **One race = one event.** If a race offers several distances, formats or disciplines
  (e.g. 30 / 60 / 100 km, or road + gravel), create a **single** competition that lists all of them
  in its `discipline_ids` and description -- do NOT create a separate event per distance or
  discipline.

## How to fill a proposal
- **All three locales (ru/kk/en).** The site stores every event and location in three languages.
  Give the event **title**, the **description** and any **venue name** in all three: `ru` (Russian),
  `kk` (Kazakh) and `en` (English). Translate faithfully; if you genuinely cannot translate a field,
  repeat the Russian text there rather than leaving it empty.
- **Announcement link (`source_url`):** the page of **THIS specific competition** on the
  organizer's own website (e.g. `https://athletex.kz/competitions/<slug>`), not the site's homepage
  and not a calendar / aggregator. If the announcement you found is a **Telegram or social-media
  post**, look for the organizer's real event page and link that instead; use a Telegram / social
  link only when the event genuinely has no web page, and even then link the specific post, never a
  channel's main page. The fetched text lists the page's real links under **"Links on the page"** --
  choose `source_url`, `url_route` and `url_registration` **only** from those real links, never type
  a URL from memory or guess one. If none of the real links is a proper event page, leave the field
  empty for the reviewer rather than inventing one.
- **Put links in their own fields.** The route / GPS-track link (e.g. a Strava link) goes in
  `url_route`, and the registration / signup link in `url_registration` -- do not bury them in the
  description text; the site has dedicated fields and buttons for them.
- **Description -- formatted HTML with the essentials.** Write it as **simple HTML**: short `<p>`
  paragraphs and a `<ul>`/`<li>` list for the groups / distances / schedule -- not one unbroken wall
  of text. Include the key facts: distances / formats, entry fee(s), start date, time and place,
  categories, **who it is for** (e.g. a required level like "2 W/kg uphill"), the rough schedule and
  the registration deadline when given. Use only `<p>`, `<br>`, `<ul>`/`<ol>`/`<li>`, `<strong>`,
  `<em>` -- never scripts or styles. Keep it informative but not a multi-page essay.
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
