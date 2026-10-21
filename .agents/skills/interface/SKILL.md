---
name: interface
description: How a page on this site should feel to the person using it - phone first, content before controls, nothing that jumps, choices that are kept, words with every icon, targets a finger can hit, text that fits in ru/kk/en and reads in every skin, the WCAG 2.2 AA baseline, states, forms and speed - and the checks that hold each rule. Read before changing a template, a stylesheet or anything a reader taps.
---

# Interface

Who the pages are for: the team expects most people to arrive from a link in a team chat, on a
phone, with one question -- "where can I ride on Saturday near Almaty, at what time, where do we
meet?". (That comes from the team's discussion, not from visit statistics: the site runs no analytics.) A
page is good when it answers that in a tap or two, in any of the three languages, in any skin.

The principles below come from the calendar redesign (issue #330) and the discussion around it. The
rules after them are the parts a test can hold; the tests so far measure the shared header of the
calendar, the list and the map, while the principles hold for every page. All of it is agreed with
the maintainer: changing a rule is a question for them, not a decision to take inside a pull
request. How skins work and who owns them is the `skins` skill.

## Principles

1. **Phone first.** Lay a page out at 375px, make sure it still works at 320px, then let it grow. A
   seven-column month grid spread October over about five phone screens with titles cut to a few
   letters; a list by days reads. On a wide screen the grid can stay -- as a choice.
2. **Content before controls.** The first screen shows events. On a phone the filters fold behind
   one button that says how many are in force ("Filters (2)"), and the ones in force show as chips
   that remove themselves on a tap. Before #330 a guest scrolled past a sign-in banner, two date
   fields and seven drop-downs to reach the first event.
3. **Say what is on screen.** The period in words ("24-25 October 2026"), the filters in force as
   chips. A reader who cannot tell what they are looking at does not trust an empty day.
4. **The usual question takes one tap.** Quick periods -- today and tomorrow, the weekend, the week,
   the month -- cover what people ask in the chat; a date picker is for everything else.
5. **Nothing moves unless the reader moved it.** Sibling views (calendar, list, map) share their
   controls, in the same place, at the same size. A view the reader chose is kept and never switched
   by the page on its own: a phone's address bar sliding away fires a resize, and a view that
   followed resizes jumped about. The same holds while a page loads: reserve the room for what
   arrives late (a label a script fills in, an image, the map) so nothing below it is pushed down.
6. **A choice is kept.** The period and the filters travel when the reader switches tabs; saved
   filters (#322) come back next visit. Making someone choose twice reads as "it lost my filter".
7. **Narrow by default, delete nothing.** Show what is near first and fold the rest ("N more in
   other countries", #332) rather than removing it: a newcomer may well travel to a race abroad.
8. **Words with every icon and every colour.** An arrow, an icon or a colour never carries meaning
   alone: next to it is visible text, or at least an `aria-label`. A `title` is not enough -- a
   phone never shows it and screen readers do not reliably read it.
9. **Built for a finger.** Anything tappable is at least 44x44px on a phone, with room between
   neighbours. WCAG 2.2 AA asks for 24px (2.5.8); 44px (2.5.5, AAA) is a deliberate choice for
   people tapping on the move, where a missed tap on a period arrow pages the wrong way.
10. **Three languages, the longest first.** Size a control for its longest label, usually Kazakh;
    a word cut off only shows in the language nobody checked.
11. **Readable in every skin.** Text at least 4.5:1 against what it is drawn on (3:1 for large
    text); a control's border, an icon and the focus ring at least 3:1 against their surroundings
    (WCAG 1.4.11) -- an outline button's border is all that says it is a button.
12. **Few words, and the right ones.** A hint takes one line. A button says what happens ("Show 12
    events", "Reset"), not "OK". Labels use the reader's words ("Weekend"), not the database's.
13. **The look belongs to the skin.** Colours, fonts and radii come from the skin's variables
    (`--bs-*`, `--skin-*`); the site's templates give structure and words. Light and dark are the
    maintainer's and do not change without them; a designer's skin is its designers'.

## Accessibility baseline

WCAG 2.2 level AA is the floor for every page and every skin; the principles above go further where
they say so. The points this site is most likely to miss:

- **Keyboard.** Everything that works with a tap works with Tab, Enter and Space, in reading order,
  with a focus ring that is always visible (`:focus-visible`) and never hidden under a sticky bar or
  an open panel (2.4.7, 2.4.11). `base.html` has no "skip to content" link yet; the first
  page-wide change to the header should add one.
- **The right element.** A link goes somewhere (`<a href>`); a button does something on this page
  (`<button type="button">`). One `<h1>` per page, headings in order, no level skipped for size --
  size is the skin's.
- **Language.** `<html lang>` follows the page's language; a block in another language (an event
  title written in Kazakh on the Russian page) carries its own `lang` when the site knows it (3.1.2).
- **Zoom.** The page reflows at 320px wide and with text at 200% without cutting anything off (1.4.4,
  1.4.10); sizes in `rem`, never a fixed height on a box that holds text.
- **Motion.** Anything that slides or fades stops under `prefers-reduced-motion: reduce`.
- **Announcements.** A change that happens without a page load -- "Link copied", a new period, a
  filter count -- is said through an `aria-live` region, as the period label already is.

## States and feedback

Every view that loads or filters has four states, and each is designed, not left to chance:

- **Loading:** the space is held (principle 5); a wait over a second shows that something is coming.
- **Empty:** says what was looked for and offers the next step -- a wider period, fewer filters --
  rather than a blank area.
- **Error:** says what failed in plain words and what to do; it never drops what the reader typed.
- **Done:** an action answers at once -- "Link copied", a saved filter -- where the reader is
  looking, and the answer reaches a screen reader too.

## Forms

Registration, event submission and the profile are where a mistake costs a reader the most.

- Every field has a visible label (`<label for>`); a placeholder is an example, not the label.
- The field's `type` and `autocomplete` match what it holds (`email`, `tel`, `given-name`,
  `bday`) so a phone offers the right keyboard and fills it in (1.3.5).
- An error sits next to its field, is tied to it (`aria-describedby`, `aria-invalid`) and says how
  to fix it (3.3.1, 3.3.3); the form keeps everything else the reader entered.
- What is required is marked before the reader submits, not discovered after.
- An action that cannot be undone (cancelling a registration, deleting an event) asks once, naming
  what will go.

## Speed on a phone

Readers open the site on a mobile network. A page should show its content within about 2.5 seconds
(LCP), not shift once shown (CLS under 0.1) and answer a tap within 200ms (INP) -- the Core Web
Vitals thresholds. In practice: images carry `width`, `height` and `loading="lazy"` below the fold;
a heavy library (FullCalendar, Leaflet) loads only on the page that uses it; a script that fills in
a label runs before the first paint or the label's room is reserved.

## Rules and their checks

| Rule | Checked by |
| --- | --- |
| Sibling views include the same partial for each shared control -- `_view_switcher.html` and, from #330, `_period_nav.html`, `_filter_toggle.html`, `_filter_chips.html` -- and switching tabs moves no control. | `tests/e2e/test_interface_rules.py::test_switching_tabs_moves_none_of_the_controls` |
| The period is named in words on every tab. | `test_the_period_is_named_in_words` |
| Every control in the shared header is at least 44x44px on a phone. | `test_every_control_is_big_enough_to_tap_on_a_phone` |
| Nothing scrolls sideways, from 320px up. | `test_no_tab_scrolls_sideways`, `test_calendar_view.py` |
| Every label fits its control in ru, kk and en. | `test_every_label_fits_its_control` |
| Every control has words: visible text or `aria-label`. | `test_every_control_says_what_it_does` |
| No hex colour in a template outside `skins/`. | pre-commit `no-hex-colours-in-templates` |
| Text at least 4.5:1 (3:1 large) in every skin. | `test_skin_contrast.py`, `test_the_header_is_readable_in_this_skin` |
| An active button keeps the border of the inactive ones: `btn-outline-secondary active`, never `btn-secondary`. Lux draws `btn-secondary` with no border, so the active tab came out 4px narrower and moved its neighbours. | `test_the_active_tab_keeps_the_border_of_the_others` |
| A hint takes one line. | `test_a_hint_takes_one_line` |
| The period and the filters travel to the other tabs. | `test_the_period_and_the_filters_travel_to_the_other_tabs` |

Not tested yet, judged in review: principles 2, 4, 7 and 12, the 3:1 for borders and icons, the
accessibility baseline, the states, forms and speed.

## Before calling a page done

- Open it at 375px and at 320px in `/kk/`: does anything scroll sideways, spill or get cut off?
- Switch between its sibling tabs, and reload it: does anything move?
- Turn two filters on and switch tabs: are the count and the chips still there?
- Look at it in the dark skin, and tab through it with the keyboard: is the focus always visible,
  and does every control say what it does?
- Empty it (a period with nothing on): does it say so and offer the next step?
- Run the checks below.

## Writing a control

- Reach for the shared partial first. A control that appears on more than one sibling page lives in
  one `_name.html` and is included; a page adds its own controls only in a slot the partial leaves
  for it (the period row's `#period-extra`, from #330).
- Measure, do not assume a size: Lux's `btn-sm` comes out 44px tall in the calendar's header, while
  the share button, styled on its own, is 36px. `2.75rem` is 44px at the browser's default 16px.
- A new colour is a new skin variable: add it to `skins/light/skin.css` and `skins/dark/skin.css`,
  which belong to the maintainer -- ask first -- and then use `var(--skin-...)` in the template.
- A new phrase needs its Russian and Kazakh (the `translations` skill); check the Kazakh fits.

## What already breaks a rule

`KNOWN` in `tests/e2e/test_interface_rules.py` and `scripts/template_colours_allowed.txt` list what
broke a rule when the rule came in. Both only shrink: a new break fails, a fixed one is dropped from
the list. They hold for light and dark only; a designer's skin gets no allowance.

Fixing an old break can change how light or dark look, and those two are the maintainer's: such a
fix waits for them, and `visual.yml` ("Light and dark unchanged") will say so.

## Running the checks

```
.venv/bin/python -m pytest tests/e2e/test_interface_rules.py -n 8
.venv/bin/python -m pytest tests/e2e/test_interface_rules.py -n 8 --device "Pixel 7"
E2E_SKIN=dark .venv/bin/python -m pytest tests/e2e/test_interface_rules.py -n 8
pre-commit run no-hex-colours-in-templates --all-files
```

The test sets its phone (375px, 320px for sideways scroll) and desktop widths itself; CI runs it in
every browser job and, via the `e2e-skin` jobs, in every skin.
