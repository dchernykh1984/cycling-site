---
name: interface
description: How a page on this site should look and behave for the person using it - widths, phone first, content before controls, nothing that jumps, choices that are kept, words with every icon, tap targets, text that fits in ru/kk/en, contrast in every skin, the qualities and named patterns of the look - each rule with why, an example and its check. Read before changing a template, a stylesheet, a layout or anything a reader taps.
---

# Interface

The team expects most readers to arrive from a link in a chat, on a phone, with one question:
"where can I ride on Saturday, at what time, where do we meet?" (an expectation, not a statistic:
the site runs no analytics). A page is good when it answers that in a tap or two, in any of the
three languages, in any skin.

Each principle below gives the rule, why it holds, an example and how it is checked. The tests
measure the shared header of the calendar, the list and the map; the principles hold for every
page. Changing a rule is a question for the maintainer, not a decision taken inside a pull request.
How skins work and who owns them is the `skins` skill; how a page behaves today is in
`specs/site/` (the `specs` skill); the general baseline every page also meets -- WCAG 2.2 AA, the
states of a view, forms, speed -- is `reference.md` next to this file.

## Widths

One page for every device, no separate version for phones or tablets.

- **Phone, from 360px: the main focus.** Every rule holds in full. The menu is folded and the
  filters sit behind one button.
  - **The narrowest phones, 320px.** Not a focus. Only one thing is checked: nothing is cut off or
    spills over -- past the screen's edge or a button's frame.
- **Desktop, from 1200px.** Every rule holds in full. The menu and the filter panel are open.
  - **Tablets, 768-1199px.** Not a focus, checked minimally: nothing scrolls sideways, nothing is
    cut off, no word breaks into letters. Held upright (768px) a tablet gets the phone layout, on
    its side (1024px) the desktop one: the layout switches at 992px, Bootstrap's `lg`.

## Principles

1. **Phone first.** Design the page for the phone, then let it grow to the desktop.
   - Why: that is where most readers open it.
   - Example: on a phone, events read as a list by days; a seven-column month grid cuts their
     names to a few letters.
   - Check: review; the widths are measured by every test below.

2. **Content before controls.** The first screen shows events; controls fold away until asked for.
   - Why: a reader came for an event, not for a form.
   - Example: on a phone the filters sit behind one button that says how many are in force
     ("Filters (2)"); those in force show as chips that remove themselves on a tap.
   - Check: review.

3. **Say what is on screen.** Name the period in words, show the filters in force, and make what is
   selected plainly selected: its fill or frame stands out from the unselected ones by at least
   3:1 (WCAG 1.4.11), not by a heavier word alone, and a screen reader is told (`aria-current`,
   `aria-pressed`).
   - Why: a reader who cannot tell what is shown does not trust an empty day. Stricter than WCAG
     1.4.11 on purpose: it measures a state against the colours next to it, this rule against the
     unselected neighbour too.
   - Example: "24-25 October 2026" above the list; the tab on screen filled, the others outlined.
   - Check: `test_the_period_is_named_in_words`, `test_what_is_selected_can_be_seen`.

4. **The usual question takes one tap.** Offer the periods people ask about as one-tap choices.
   - Why: "what is on this weekend" should not need a date picker.
   - Example: today and tomorrow, the weekend, the week, the month; a date picker for the rest.
   - Check: review.

5. **Nothing moves unless the reader moved it.** Sibling views share their controls, in the same
   place and at the same size; the page never changes the view on its own; room is held for what
   arrives late.
   - Why: a control that jumps reads as a different page, and what moved reads as gone.
   - Example: the calendar, the list and the map include one partial for each shared control
     (`_page_heading.html`, `_view_switcher.html`, `_period_nav.html`, `_filter_toggle.html`,
     `_filter_chips.html`); a phone's address bar sliding away fires a resize, and the view the
     reader chose stays.
   - Check: `test_switching_tabs_moves_none_of_the_controls`,
     `test_the_active_tab_keeps_the_border_of_the_others`.

6. **A choice is kept, and a link wins.** What a link names -- the period, the filters -- is what
   opens, whatever was chosen before; a choice made on the page travels between sibling tabs and
   stays for the visit; a filter the reader saved comes back on the next.
   - Why: choosing twice reads as "it lost my filter", and a link that opens something else reads
     as the wrong link.
   - Example: the weekend picked on the list is the weekend on the map; a link to the weekend's
     races opens the weekend for a reader who last looked at the month.
   - Check: `test_the_period_and_the_filters_travel_to_the_other_tabs`.

7. **Narrow by default, delete nothing.** Show what is near first and fold the rest; never remove
   it. What counts as near comes from the reader's preferences or a setting, never from the code.
   - Why: a newcomer may travel to a race abroad; the site is for anyone, anywhere (the
     constitution's principle VI).
   - Example: "N more in other countries" under the region's events; no city written into a
     template.
   - Check: review.

8. **Words with every icon and every colour.** An icon, an arrow or a colour never carries meaning
   alone: visible text beside it, or an `aria-label` only where there are no words. Where there
   are, the name a screen reader gets begins with them (WCAG 2.5.3). A `title` is not enough.
   - Why: a screen reader, and a reader who cannot tell colours apart, get nothing from a shape or
     a hue; a phone never shows a `title`; an `aria-label` that says something else replaces what
     is on screen, and a reader who speaks to the page says the visible words.
   - Example: the share icon is labelled "Share".
   - Check: `test_every_control_says_what_it_does`.

9. **Built for a finger and a mouse.** Every control answers a tap across at least 44x44px on a
   phone and a click across at least 24x24px on a desktop. The zone is centred on the control and
   the zones of neighbours do not overlap. Nothing that matters is reachable only by hovering.
   - Why: people tap on the move, and a missed tap does the wrong thing; a phone has no hover. WCAG
     2.2 AA asks for 24px (2.5.8); 44px is 2.5.5 (AAA) and Apple's minimum for the iPhone and
     iPad; Material asks 48dp, and 44 is the site's choice. A link inside a sentence is exempt, as
     2.5.8 exempts it.
   - Example: a slim 32px pill with an invisible 44px zone around it, rows far enough apart that
     the zones do not meet.
   - Check: `test_every_control_is_big_enough_to_tap`.

10. **Three languages, the longest first.** Size a control for its longest label, usually Kazakh.
    - A group of buttons that belong together stays in one row on a phone and a desktop.
      A list of choices that grows with the data -- the categories of a protocol -- is not such a
      group: it wraps onto as many rows as it needs, never scrolling sideways.
    - Inside a button the words take at most two lines, spaced at least 1.2 apart, at least 8px
      from the frame at the sides and 4px above and below; the button grows to hold them, and the
      buttons of a row share a height.
    - When a label would need a third line, or come closer to the frame, in any language at 360px:
      shorten the words in all three catalogues and make the type smaller -- for the whole row,
      never below 12px, one step above the smallest size in Apple's (11pt) and Google's (11sp)
      type scales. The floor is for type made smaller to fit, not for labels a skin sets small on
      purpose.
    - At 320px a label only must not be cut off or spill over its frame.
    - Why: a word cut off shows only in the language nobody checked; a row folded in two reads as
      a grid.
    - Example: "Today tomorrow" in two lines inside its button, in all three languages.
    - Check: `test_every_label_fits_its_control`, `test_a_button_group_stays_in_one_row`,
      `test_no_word_breaks_into_letters`, `test_no_tab_scrolls_sideways`.

11. **Readable in every skin, in every state.** Text at least 4.5:1 against what it is drawn on
    (3:1 for large text), at rest and under the pointer. A boundary needs 3:1 only where nothing
    else shows the control: a text field, a checkbox, a button that is an icon alone -- then the
    icon itself. A button with words is known by its words: its border may be as light as the skin
    draws it, but it stays. What shows a selection needs 3:1 always.
    - Why: below these, words and controls vanish on a phone in daylight; WCAG 1.4.11 asks for a
      boundary only where nothing else identifies the control, and a light one still shows where
      to tap.
    - Example: pale text that turns white on light grey under the pointer fails; a beige border
      around a "Filters" button passes.
    - Exception: moving through the controls with the Tab key, and the focus ring, are not checked
      yet. Both are AA (2.4.7 Focus Visible, 2.4.11 Focus Not Obscured), so until they are, the
      baseline in `reference.md` is AA less these two.
    - Check: `test_the_header_is_readable_in_this_skin`, `test_every_border_can_be_seen`,
      `test_skin_contrast.py`.

12. **Few words, and the right ones.** A hint takes one line; a button says what happens; labels
    use the reader's words; two controls on one screen never share a name when they do different
    things; dates and times come in the reader's order and words -- the month in its Russian case,
    the year first in Kazakh, the 24-hour clock, an en dash for a range.
    - Why: a reader acts on the words, and one name for two actions leads to the wrong place.
    - Example: "Show 12 events", not "OK"; "Weekend", not the database's term; a view switch
      inside the calendar is not called "List" next to a "List" tab.
    - Check: `test_a_hint_takes_one_line`; the rest in review.

13. **The look belongs to the skin.** Colours, fonts and radii come from the skin's variables
    (`--bs-*`, `--skin-*`); the site's templates give structure and words. Light and dark are the
    maintainer's; a designer's skin is its designers'.
    - Why: a colour written into a shared template paints every skin the same.
    - Example: `var(--bs-border-color)` in a template, never `#dee2e6`.
    - Check: pre-commit `no-hex-colours-in-templates`.

## Look

The look is described as qualities with a measure and patterns with a name, not as "like site X".
The values -- colours, fonts, radii, spacing -- are the skin's (principle 13).

### Qualities

| Quality | What it means | How to tell |
| --- | --- | --- |
| **Calm** | Neutral surfaces; colour is kept for meaning -- the event's type, its sport, what is "ours" -- and for the one main action. | At most one filled button for the main action per view -- a selected segment does not count; every colour on screen can be named for what it means. |
| **Readable at arm's length** | In a list, the date, the sport and the title are what the eye lands on; everything else is quieter. | Squint test: blur a 360px screenshot -- date, sport and title still stand apart from the rest. |
| **Clear type** | Few sizes, set apart by weight and size together; dates and times in figures of equal width, so columns of them line up. | At most two font families; every text size on the page can be named for its job: title, body, label, caption. |
| **Even rhythm** | One spacing scale, one radius, one way of building each pattern; edges line up down the page. | The same pattern looks the same on every page it appears; no one-off margins in a template. |
| **Dense, not crowded** | A phone screen carries several events, each still easy to tap. | At 360x640px, at least three events are visible below the header on the first screen of a list. |

### Patterns

Each pattern has a name to use in review ("this wants the event card"), the sites where it was
seen, and where it lives or will live here.

| Pattern | What it is | Seen at | Here |
| --- | --- | --- | --- |
| **Event card** | Date block on the left, sport icon, title, one line of place (and organiser), one action on the right; the whole card opens the event. | BikeReg, Orgeo, RussiaRunning | #331 |
| **Day header** | A list grouped by day under a quiet header ("Sat, 24 October"); a multi-day race is one row with its range. | Zwift | the List tab on a phone |
| **Quick periods** | One row of segments: today and tomorrow, weekend, week, month. | Meetup, Eventbrite | `_period_nav.html` |
| **View switch** | Segments for the sibling views; the one on screen marked, all the same size. | BikeReg | `_view_switcher.html` |
| **Filter button with a count** | One button on a phone, "Filters (2)", instead of a row of drop-downs. | BikeReg, Zwift, RussiaRunning, Miles Republic | `_filter_toggle.html` |
| **Filter chips** | The filters in force as chips in one line, each removed with a tap. | Meetup | `_filter_chips.html` |
| **"+N more"** | A month cell shows at most three events and a count of the rest. | the calendar library's own day limit | the month grid |
| **Sport icon with its name** | A square icon from one icon set, always with the sport's name beside it or as its label. | Orgeo, Strava | #331 |
| **Organiser** | "by ..." under the title, and a filter for one's own club. | Meetup, BikeReg, Strava | #336 |
| **Status badge** | A small badge for what is time-limited or open: registration open, closing in N days. | Orgeo, Eventbrite | not planned yet |
| **Time first for a ride** | The meeting time large, the pace or group as a badge. | Zwift, Strava | the time stays free text in the announcement (the maintainer's choice); the link preview carries it (#318) |
| **Page action** | What acts on the whole page -- share it, subscribe to it -- sits at the right end of the heading's row, apart from the navigation, centred on the middle of the heading's capital letters. | Apple's and Google's design guides, Airbnb | `_page_heading.html` |
| **Subscribe and add to calendar** | Subscription to the filtered calendar and "add to my calendar" near the top, not in the footer. | Orgeo | #333 |

A pattern not in this table gets a name, a row here and a partial of its own before it appears on a
second page.

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
  for it.
- Mark the active one with `active` on the same class as the others: a different class can draw a
  different border and move its neighbours.
- Measure, do not assume a size: the same `btn-sm` comes out at different heights in different
  skins. `2.75rem` is 44px at the browser's default 16px.
- A slim control gets its 44px from an invisible layer around it, not by growing; keep rows of
  controls far enough apart that those layers do not overlap.
- A button that toggles says whether it is on: `aria-pressed` (a period kind) or `aria-expanded`
  (the filter panel), changed by the same script that changes its look.
- A hover style sits under `@media (hover: hover)`: on a phone `:hover` sticks after a tap, and the
  reader sees it as the control's new state.
- Sibling views are links with `aria-current="page"`, not `role="tab"`: each is its own address,
  and the tabs pattern is for panels on one page.
- A font a skin brings must carry the Kazakh letters (U+04D8, U+0492, U+049A, U+04A2, U+04E8,
  U+04B0, U+04AE, U+04BA, U+0406 and their lower case): without them the browser draws those
  letters in another font, and the words change width unseen.
- A new colour is a new skin variable: add it to `skins/light/skin.css` and `skins/dark/skin.css`,
  which belong to the maintainer -- ask first -- and then use `var(--skin-...)` in the template.
- A new phrase needs its Russian and Kazakh (the `translations` skill); check the Kazakh fits.

## What already breaks a rule

`KNOWN` in `tests/e2e/test_interface_rules.py` and `scripts/template_colours_allowed.txt` list what
broke a rule when the rule came in. Both only shrink: a new break fails, a fixed one is dropped from
the list. Each entry names its skin: a break the site's own templates cause is listed for every skin
it shows in, a break a skin's own CSS causes only for that skin. A colour entry -- text, an icon, a
boundary, a selection -- is allowed for light and dark only: a designer's skin gets no allowance
for its own colours.

Fixing an old break can change how light or dark look, and those two are the maintainer's (the
constitution's principle II): such a fix waits for them, and the pull request says so in words.

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


## Calendar layout (issue #330)

A fresh phone visit opens readable days; Month explicitly opens the grid. Keep the chosen layout
for the browser session and do not switch it on resize. The List tab keeps full event facts in
expandable row details, with city and sport visible beside the title. These are the reviewed choices
in `specs/330-mobile-calendar/spec.md`; light/dark selection fills and frames were approved by the
maintainer on 2026-10-24.
