# Agent guidance

Edit this file to steer what the events agent proposes. It is re-read on every run and passed to
the model as instructions, so you can nudge it (e.g. "look at the calendar page of site X",
"include gravel races") without changing code. You may write in Russian.

## Priority
Two ladders describe what matters most -- but they are about ORDER, and the order is already handled
for you: the system scans the Kazakh and Kyrgyz sources first and stops once the run's budget is
full, so the closer, cycling events naturally win a limited budget. **Your job is the opposite: from
whatever page you are given, extract every real, in-scope event you can find. Never drop an event
because it is far away or not cycling** -- a Reykjavik marathon on a foreign-running page is exactly
as extractable as an Almaty gran fondo, and leaving it out is a bug. The ladders below rank things
when everything is on the table; they never mean "skip this one."

- **By geography (rank, not a filter):** Kazakhstan (Almaty above all) -> Kyrgyzstan -> Russia and
  China -> the rest of the world. Every step is in scope; a far country is still a real event to
  extract.
- **By sport (rank, not a filter):** cycling first; then running, triathlon and cross-country
  skiing. All four are in scope.

## What to propose
- Real, **upcoming** competitions:
  - **cycling** -- road, MTB, gravel, cyclocross, gran fondo, brevets, bikepacking, etc.;
  - **running** -- marathons, half marathons, trail and mountain running, ultras;
  - **triathlon** and its relatives (duathlon, aquathlon, swimrun);
  - **cross-country skiing** -- races and ski marathons.
  Anywhere in the world, in any of these sports -- extract it. Whether it is a marathon in Iceland,
  a triathlon in Turkey or a ski race in Russia, if the page lists a real upcoming event, propose it.
  The system decides how many make it in and in what order; you never have to.

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
  This is about who the *event* is for, not about who happens to be racing in it: an open mass start
  that anyone can enter stays in scope even when a national championship is contested inside it.
- **Do NOT add past events** -- only upcoming ones, never events that already happened.
- Off-topic posts, chat replies, group rules ("Правила группы") and vague personal chatter
  (e.g. "завтра в 5:00 стартуем из-под дуба") -- only real announcements with a place and a date.
- Anything you are not confident is a real event with a concrete date.
- **No place at all / only a draft page.** Skip an announcement that never says where the event is
  held, and one whose organizer page is just a draft or placeholder without real details. This is
  about the event being too vague to be real -- it is not about whether the site already has the
  city. A race with a named place still counts even when you cannot pin the region: propose it and
  put the place in the description (see "Location" below).
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
  a URL from memory or guess one. On a Telegram feed each post is headed by `--- post <address>`;
  that address is the post's own and is what to use when the post links no event page of its own.
  If none of the real links is a proper event page, leave the field
  empty for the reviewer rather than inventing one.
- **Put links in their own fields.** The route / GPS-track link -- a Strava or RideWithGPS route, a
  `.gpx`/`.kml` file, or a route.eduha track-editor link -- goes in `url_route`, and the registration
  / signup link in `url_registration`; do not bury them in the description. The route link matters
  beyond display: the start line of that track is read as the venue's map coordinate, so always
  capture it when the page has one.
- **Description -- formatted HTML with the essentials.** Write it as **simple HTML**: short `<p>`
  paragraphs and a `<ul>`/`<li>` list for the groups / distances / schedule -- not one unbroken wall
  of text. Include the key facts: distances / formats, entry fee(s), start date, time and place,
  categories, **who it is for** (e.g. a required level like "2 W/kg uphill"), the rough schedule and
  the registration deadline when given. Use only `<p>`, `<br>`, `<ul>`/`<ol>`/`<li>`, `<strong>`,
  `<em>` -- never scripts or styles. Keep it informative but not a multi-page essay.
- **Location -- name the real place.** The site's locations are a tree: country -> region -> city ->
  specific venue (the start point). Give the **real** country, region, city and the **specific start
  venue / address**, and repeat them in the (Russian) description.
  - **region** means the first-level division of the country -- oblast, krai, republic, state,
    province, county. A district, raion, rural settlement or park is NOT a region: that belongs in
    the venue, with its actual region above it. "Уфимский район" is not a region, "Республика
    Башкортостан" is.
  - **A city that is a region in its own right repeats itself.** Federal cities and capitals that
    the country administers separately are their own first-level unit, so give the same name twice:
    Россия -> Москва -> Москва, Россия -> Санкт-Петербург -> Санкт-Петербург, Казахстан -> Астана ->
    Астана, Казахстан -> Алматы -> Алматы, Казахстан -> Шымкент -> Шымкент. Naming the surrounding
    oblast instead ("Московская область" for Москва) points at a different place.
  - **A city the site does not have yet is fine.** Name it and it goes for review, so the race is
    placed from the start. Never bend a race into a wrong neighbouring city to avoid this.
  - **A city is only placed together with its region, so always name both.** The site cannot file a
    city without the first-level region above it. The announcement often names only the city (or only
    the start place) -- give the region anyway: a city's region is geographic fact you know, not a
    guess. Узуд (Ouzoud) is in Марокко -> Бени-Меллаль-Хенифра; Марракеш is in Марокко -> Марракеш-
    Сафи; a town near a capital sits in that capital's oblast. Fill in country, region and city
    whenever you can name the town at all, even if the page only prints the town.
  - **Only leave the place empty when the town itself is genuinely unknown** -- not merely because the
    announcement did not spell out the region. When you do leave it empty, **repeat the start place in
    the (Russian) description** -- e.g. "Место старта: <город/место>" -- since that line is all the
    reviewer has to place it by.
  - **Never answer with a placeholder.** "Другая страна" / "Другой регион" / "Другой город" /
    "Другая локация" are not place names -- writing one creates a location called that. Leave the
    field empty instead.
  - **Use the current, official spelling** the site is likely to hold, for the region as well as the
    city: "Алматы" (not "Алма-Ата"), "Астана" (not "Нур-Султан"), "Талгар" (not "г. Талгар"). Give a
    real, current first-level region -- do not invent one -- and name it plainly (e.g. "Алматинская
    область"), since a variant spelling risks a duplicate of a region already on the site.
  - Countries are never created from an announcement, and almost every country is already on the
    site, so name the country properly and the race will place under it. In the rare case the site
    does not carry that country, the race is left without a location for a reviewer to add the
    country and place it -- so also put the start place in the (Russian) description as a fallback.


## Hints
- (add source-specific hints here, e.g. "on granfondo.com.kz the schedule is under /ru/calendar")
