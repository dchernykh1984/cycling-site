---
name: interface
description: How a page on this site should look and behave for the person using it - the qualities and named patterns of its look, mobile layout first, content before controls, nothing that jumps, choices that are kept, words with every icon, tap targets, text that fits in ru/kk/en, contrast and accessibility in every skin - and the checks that hold each rule. Read before changing a template, a stylesheet, a layout or anything a reader taps.
---

# Interface

Who the pages are for: the team expects most people to arrive from a link in a team chat, on a
phone, with one question -- "where can I ride on Saturday near Almaty, at what time, where do we
meet?". (That comes from the team's discussion, not from visit statistics: the site runs no
analytics.) A page is good when it answers that in a tap or two, in any of the three languages, in
any skin.

The principles come from the calendar redesign (issue #330) and the discussion around it; where a
principle names a control that #330 adds, it says so. The rules after them are the parts a test can
hold -- so far measured on the shared header of the calendar, the list and the map, while the
principles hold for every page. Changing a rule is a question for the maintainer, not a decision to
take inside a pull request. How skins work and who owns them is the `skins` skill.

`reference.md` next to this file holds the general baseline every page also meets: WCAG 2.2 AA,
the four states of a view, forms and speed on a phone. Read it when building a page, a form or
anything that loads.

## Widths

The site is one page for every device, with no separate version for phones or tablets -- as
Meetup, Eventbrite and Zwift are built.

- **Phone, from 360px: the main focus.** Every rule holds in full. The menu is folded and the
  filters sit behind one button.
  - **The narrowest phones, 320px.** Not a focus. Only one thing is checked: nothing is cut off or
    spills over -- past the screen's edge or a button's frame.
- **Desktop, from 1200px.** Every rule holds in full. The menu and the filter panel are open.
  - **Tablets, 768-1199px.** Not a focus, checked minimally: nothing scrolls sideways, nothing is
    cut off, no word breaks into letters. A tablet held upright (768px) gets the phone layout, one
    turned on its side (1024px) the desktop one: the layout switches at 992px, Bootstrap's `lg`.

## Principles

1. **Phone first.** Design a page for the phone first, then let it grow. A seven-column month grid
   spread October over about five phone screens with titles cut to a few letters; a list by days
   reads. On a wide screen the grid can stay -- as a choice.
2. **Content before controls.** The first screen shows events. On a phone the filters fold behind
   one button that says how many are in force ("Filters (2)"), and the ones in force show as chips
   that remove themselves on a tap (both from #330). Before #330 a guest scrolled past a sign-in
   banner, two date fields and seven drop-downs to reach the first event.
3. **Say what is on screen.** The period in words ("24-25 October 2026", the period row from #330),
   the filters in force as chips. A reader who cannot tell what they are looking at does not trust
   an empty day. What is selected -- the tab on screen, the period kind, a filter -- is plainly
   selected: its fill or its frame stands out from the unselected ones by at least 3:1 (WCAG
   1.4.11), not by a heavier word alone, and it says so to a screen reader (`aria-current`,
   `aria-pressed`). In #343's first version the active tab got a white frame on white and looked
   like plain text.
4. **The usual question takes one tap.** Quick periods -- today and tomorrow, the weekend, the week,
   the month (from #330) -- cover what people ask in the chat; a date picker is for everything else.
5. **Nothing moves unless the reader moved it.** Sibling views (calendar, list, map) share their
   controls, in the same place, at the same size. A view the reader chose is kept and never switched
   by the page on its own: a phone's address bar sliding away fires a resize, and a view that
   followed resizes jumped about. The same holds while a page loads: reserve the room for what
   arrives late (a label a script fills in, an image, the map) so nothing below it is pushed down.
6. **A choice is kept.** The period and the filters travel when the reader switches tabs; saved
   filters (#322) come back next visit. Making someone choose twice reads as "it lost my filter".
7. **Narrow by default, delete nothing.** Show what is near first and fold the rest ("N more in
   other countries", #332) rather than removing it: a newcomer may well travel to a race abroad.
   What counts as near is never written into a template or a view -- no fixed Almaty: a region, a
   city or a club comes from the reader's preferences or from a setting the maintainer can change
   (the constitution's principle VI, the `specs` skill).
8. **Words with every icon and every colour.** An arrow, an icon or a colour never carries meaning
   alone: next to it is visible text, or at least an `aria-label`. A `title` is not enough -- a
   phone never shows it and screen readers do not reliably read it.
9. **Built for a finger and a mouse.** Every control answers a tap across at least 44x44px on a
   phone and a click across at least 24x24px on a desktop. How big it is drawn is the skin's
   choice: a slim 32px pill with an invisible 44px zone around it is fine. The zone is centred on
   the control and the zones of neighbours do not overlap -- rows of controls stand far enough
   apart. Nothing that matters is reachable only by hovering: a phone has no hover. WCAG 2.2 AA
   asks for 24px (2.5.8); 44px (2.5.5, AAA) is Apple's minimum for the iPhone and iPad, and our
   deliberate choice for the phone, where people tap on the move.
10. **Three languages, the longest first.** Size a control for its longest label, usually Kazakh;
    a word cut off only shows in the language nobody checked.
    - A group of buttons that belong together -- the period kinds, the view switch -- stays in one
      row on a phone (360px and up) and a desktop (1200px and up); it never folds into a second row.
    - Inside a button the words take at most two lines, spaced at least 1.2 apart, at least 8px
      from the frame at the sides and 4px above and below; the button grows to hold them, and the
      buttons of a row share a height.
    - When a label would need a third line, or come closer to the frame than that, in any language
      at 360px, shorten the words (in all three catalogues) and make the type smaller -- for every
      button of the row at once, so the row stays even, and never below 12px, the smallest label
      size in Apple's and Google's type scales. The 12px floor is for type made smaller to fit; it
      does not reach labels a skin sets small on purpose (Lux's 10px capitals). Before #343 settled
      on "Today tomorrow", "Today and tomorrow" took a third line in Kazakh and English at 320px and
      was cut off.
    - At 320px the room around the words is not asked for: a label only must not be cut off or
      spill over its frame.
11. **Readable in every skin, in every state.** Text at least 4.5:1 against what it is drawn on
    (3:1 for large text) at rest and under the pointer -- a button that is readable at rest can
    turn white on pale grey when hovered (1.49:1 on the view tabs in light). A boundary needs 3:1
    only where nothing else shows the control: a text field, a checkbox, a button that is an icon
    alone -- then the icon itself needs 3:1. A button with words is known by its words: its border
    needs no 3:1 and may be as light as the skin draws it, but it is not removed -- it shows where
    to tap (WCAG 1.4.11 and its Understanding notes). What shows a selection needs 3:1 always.
    Exception: moving through the controls with the Tab key, and the focus ring, are not checked
    for now.
12. **Few words, and the right ones.** A hint takes one line. A button says what happens ("Show 12
    events", "Reset"), not "OK". Labels use the reader's words ("Weekend"), not the database's.
13. **The look belongs to the skin.** Colours, fonts and radii come from the skin's variables
    (`--bs-*`, `--skin-*`); the site's templates give structure and words. Light and dark are the
    maintainer's and do not change without them; a designer's skin is its designers'.

## Look

"Make it look like Strava" is not something a template can follow or a reviewer can check. What
the sports sites we looked at have in common is described here instead, as qualities with a
measure and as patterns with a name. The values -- colours, fonts, radii, spacing -- are the
skin's (principle 13); this section is about what any skin draws.

### Qualities

| Quality | What it means | How to tell |
| --- | --- | --- |
| **Calm** | Neutral surfaces; colour is kept for meaning -- the event's type, its sport, what is "ours" -- and for the one main action. | At most one filled button for the main action per view -- a selected segment does not count; every colour on screen can be named for what it means. |
| **Readable at arm's length** | In a list, the date, the sport and the title are what the eye lands on; everything else is quieter. | Squint test: blur a 360px screenshot -- date, sport and title still stand apart from the rest. |
| **Clear type** | Few sizes, set apart by weight and size together; dates and times in figures of equal width, so columns of them line up. | At most two font families and five text sizes on a page. |
| **Even rhythm** | One spacing scale, one radius, one way of building each pattern; edges line up down the page. | The same pattern looks the same on every page it appears; no one-off margins in a template. |
| **Dense, not crowded** | A phone screen carries several events, each still easy to tap. | At 360px, at least three events are visible below the header on the first screen of a list. |

### Patterns

Each pattern has a name to use in review ("this wants the event card"), the sites where we saw it
(the calendar redesign report, October 2026) and where it lives or will live here.

| Pattern | What it is | Seen at | Here |
| --- | --- | --- | --- |
| **Event card** | Date block on the left, sport icon, title, one line of place (and organiser), one action on the right; the whole card opens the event. | BikeReg (date at the left, type label, organiser's logo), Orgeo (square sport icon), RussiaRunning (large cards with date and city) | #331 |
| **Day header** | A list grouped by day under a quiet header ("Sat, 24 October"); a multi-day race is one row with its range. | Zwift (day headers on a phone) | list view, #330 |
| **Quick periods** | One row of segments: today and tomorrow, weekend, week, month. | Meetup, Eventbrite ("Today / Tomorrow / This weekend") | `_period_nav.html`, #330 |
| **View switch** | Segments for list, month, map; the one on screen marked, all the same size. | BikeReg (list / map switch) | `_view_switcher.html` |
| **Filter button with a count** | One button on a phone, "Filters (2)", instead of a row of drop-downs. | BikeReg, Zwift ("Filter events" at the bottom of the screen), RussiaRunning, Miles Republic ("Filters 11") | `_filter_toggle.html`, #330 |
| **Filter chips** | The filters in force as chips in one line, each removed with a tap. | Meetup (filters as chips in one line) | `_filter_chips.html`, #330 |
| **"+N more"** | A month cell shows at most three events and a count of the rest. | the calendar library's own day limit | month grid, #330 |
| **Sport icon with its name** | A square icon from one icon set, always with the sport's name beside it or as its label. | Orgeo (square icons), Strava (an icon on every activity) | #331 |
| **Organiser** | "by ..." under the title, and a filter for one's own club. | Meetup ("by ..."), BikeReg (organiser's logo), Strava (club events) | #336 |
| **Status badge** | A small badge for what is time-limited or open: registration open, closing in N days. | Orgeo (days left to register), Eventbrite ("Sales end soon") | not planned yet |
| **Time first for a ride** | The meeting time large, the pace or group as a badge. | Zwift (time first, group badge), Strava (start point, pace groups) | the time stays free text in the announcement (the maintainer's choice); the link preview carries it (#318) |
| **Page action** | What acts on the whole page -- share it, subscribe to it -- sits at the right edge of the heading's row, apart from the navigation (tabs, period), so the heading's length never moves it and a tap meant for a tab never shares; it is centred on the middle of the heading's capital letters, as Apple centres its symbols beside text. | Apple's and Google's design guides (actions at the trailing end of the top bar), Airbnb (Share and Save at the right of a listing's title) | `_page_heading.html`, #343 |
| **Subscribe and add to calendar** | Subscription to the filtered calendar and "add to my calendar" near the top, not in the footer. | Orgeo (sync with the phone's calendar, RSS) | #333 |

A pattern not in this table gets a name, a row here and a partial of its own before it appears on a
second page.

## Rules and their checks

| Rule | Checked by |
| --- | --- |
| Sibling views include the same partial for each shared control -- `_view_switcher.html` and, from #330, `_period_nav.html`, `_filter_toggle.html`, `_filter_chips.html` -- and switching tabs moves no control. | `tests/e2e/test_interface_rules.py::test_switching_tabs_moves_none_of_the_controls` |
| The period is named in words on every tab. | `test_the_period_is_named_in_words` |
| Every control in the shared header answers a tap across 44x44px on a phone and 24x24px on a desktop; the zones of neighbours do not overlap. | `test_every_control_is_big_enough_to_tap` -- where a tap lands, not how big the frame is |
| Nothing scrolls sideways, nothing is cut off, no word breaks into letters -- at 320, 768 and 1024px only these; at 360 and 1280px every rule. | `test_no_tab_scrolls_sideways`, `test_every_label_fits_its_control`, `test_calendar_view.py` |
| A group of buttons that belong together stays in one row, from 360px up. | `test_a_button_group_stays_in_one_row` |
| Every label fits its control in ru, kk and en, from 360px up: at most two lines, spaced at least 1.2, at least 8px from the frame at the sides and 4px above and below; at 320px nothing is cut off or spills over its frame. | `test_every_label_fits_its_control` |
| Every control has words: visible text or `aria-label`. | `test_every_control_says_what_it_does` |
| No hex colour in a template outside `skins/`. | pre-commit `no-hex-colours-in-templates` |
| Text at least 4.5:1 (3:1 large) in every skin, at rest and under the pointer. | `test_skin_contrast.py`, `test_the_header_is_readable_in_this_skin` |
| A control without words -- a field, a checkbox, an icon button -- has a boundary or an icon at least 3:1 against what surrounds it. | `test_every_border_can_be_seen` -- leaves out controls with visible words |
| What is selected stands out from the unselected by at least 3:1 in its fill or its frame, and carries `aria-current` or `aria-pressed`. | `test_what_is_selected_can_be_seen` |
| An active button keeps the border of the inactive ones: `btn-outline-secondary active`, never `btn-secondary`. Lux draws `btn-secondary` with no border, so the active tab came out 4px narrower and moved its neighbours. | `test_the_active_tab_keeps_the_border_of_the_others` |
| A hint takes one line. | `test_a_hint_takes_one_line` |
| The period and the filters travel to the other tabs. | `test_the_period_and_the_filters_travel_to_the_other_tabs` |

Not tested yet, judged in review: principles 2, 4, 7 and 12, the patterns, what is reachable only
by hovering, and everything in `reference.md`. The Tab key and the focus ring are left out for now
(principle 11).

## Before calling a page done

- Open it at 360, 768 and 1024px and at 320px in `/kk/`: does anything scroll sideways, spill or
  get cut off?
- Switch between its sibling tabs, and reload it: does anything move?
- Turn two filters on and switch tabs: are the filters still in force?
- Look at it in the dark skin: does every control say what it does and, if it toggles, whether it
  is on?
- Empty it (a period with nothing on): does it say so and offer the next step?
- Run the checks below.

## Writing a control

- Reach for the shared partial first. A control that appears on more than one sibling page lives in
  one `_name.html` and is included; a page adds its own controls only in a slot the partial leaves
  for it (the period row's `#period-extra`, from #330).
- Measure, do not assume a size: Lux's `btn-sm` comes out 44px tall in the calendar's header, while
  the share button, styled on its own, is 36px. `2.75rem` is 44px at the browser's default 16px.
- A slim control gets its 44px from an invisible layer around it, not by growing; keep rows of
  controls far enough apart that those layers do not overlap.
- A button that toggles says whether it is on: `aria-pressed` (favourite, a period kind) or
  `aria-expanded` (the filter panel), changed by the same script that changes its look.
- A new colour is a new skin variable: add it to `skins/light/skin.css` and `skins/dark/skin.css`,
  which belong to the maintainer -- ask first -- and then use `var(--skin-...)` in the template.
- A new phrase needs its Russian and Kazakh (the `translations` skill); check the Kazakh fits.

## What already breaks a rule

`KNOWN` in `tests/e2e/test_interface_rules.py` and `scripts/template_colours_allowed.txt` list what
broke a rule when the rule came in. Both only shrink: a new break fails, a fixed one is dropped from
the list. Each entry names its skin: a break the site's own templates cause is listed for every
skin it shows in, a break a skin's own CSS causes only for that skin. A colour entry -- text, an
icon, a boundary, a selection -- is allowed for light and dark only: a designer's skin gets no
allowance for its own colours.

Fixing an old break can change how light or dark look, and those two are the maintainer's
(the constitution's principle II): such a fix waits for them. No check stops it any more -- the
screenshot comparison of light and dark was retired -- so the pull request says it in words.

## Running the checks

```
.venv/bin/python -m pytest tests/e2e/test_interface_rules.py -n 8 --reuse-db
.venv/bin/python -m pytest tests/e2e/test_interface_rules.py -n 8 --reuse-db --device "Pixel 7"
E2E_SKIN=dark .venv/bin/python -m pytest tests/e2e/test_interface_rules.py -n 8 --reuse-db
pre-commit run no-hex-colours-in-templates --all-files
```

`--reuse-db` keeps the test database between runs: creating it costs about 50 seconds a start.
The test sets its widths itself -- 360 and 1280px for every rule; 320, 768 and 1024px for what
scrolls sideways, is cut off or breaks into letters -- and CI runs it in every browser job and, via
the `e2e-skin` jobs, in every skin.
