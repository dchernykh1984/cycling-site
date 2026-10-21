# Interface reference

The general baseline behind the `interface` skill: what every page, form and view on this site meets
whatever it shows. SKILL.md holds what is particular to this site; this file is the common ground.
None of it is tested automatically yet: it is judged in review.

## Accessibility baseline: WCAG 2.2 AA

Level AA is the floor for every page and every skin; the skill's principles go further where they
say so. The points this site is most likely to miss:

- **Keyboard.** Everything that works with a tap works with Tab, Enter and Space, in reading order
  (2.4.3), with a focus ring that is always visible (`:focus-visible`) and never hidden under a
  sticky bar or an open panel (2.4.7, 2.4.11). `base.html` has no "skip to content" link yet; the
  first page-wide change to the header should add one -- it stays invisible until focused, so light
  and dark look the same.
- **The right element.** A link goes somewhere (`<a href>`); a button does something on this page
  (`<button type="button">`). One `<h1>` per page, headings in order, no level skipped for size --
  size is the skin's.
- **Name, role, state (4.1.2).** A control built from a `<div>` or a styled `<button>` says what it
  is and what state it is in: a toggle carries `aria-pressed`, a control that opens a panel
  `aria-expanded`, the current tab `aria-current="page"`.
- **Images (1.1.1).** An image that says something has an `alt` that says it; an image that only
  repeats the text beside it -- a news card's picture next to its title -- has `alt=""`, or a
  screen reader reads the title twice. An `<img>` never goes without `alt`.
- **Links that say where they go (2.4.4).** A row of "More ->" links reads as one word repeated:
  each carries the event's name, visible or in a `visually-hidden` span.
- **Language (3.1.2).** `<html lang>` follows the page's language; a block in another language (an
  event title written in Kazakh on the Russian page) carries its own `lang` when the site knows it.
- **Zoom (1.4.4, 1.4.10).** The page reflows at 320px wide and with text at 200% without cutting
  anything off: sizes in `rem`, never a fixed height on a box that holds text.
- **No dragging needed (2.5.7).** Whatever is done by dragging -- panning the map, placing a venue
  -- can also be done by taps: Leaflet's zoom buttons stay, and a venue's point is set by a click.
- **Content on hover or focus (1.4.13).** A tooltip or popover can be dismissed with Escape, can be
  hovered without vanishing, and stays until the reader moves away -- a tap shows it on a phone.
- **Motion.** Bootstrap (and Lux on top of it) already turns its own transitions off under
  `prefers-reduced-motion: reduce`. Our own CSS and scripts do the same, and so does any library
  animation we start -- a map that glides with Leaflet's `flyTo` jumps with `setView` instead.
- **Announcements.** A change that happens without a page load -- "Link copied", a new period, a
  filter count -- is said through an `aria-live` region, as the period label is from #330.

## States and feedback

Every view that loads or filters has four states, and each is designed, not left to chance:

- **Loading:** the space is held (the skill's principle 5); a wait over a second shows that
  something is coming.
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
- What the site already knows is not asked again: a signed-in rider's name and birth date are
  filled in from the profile, not typed a second time (3.3.7).
- Signing in needs no puzzle and no retyping from memory: a password can be pasted and filled by a
  password manager (`autocomplete="current-password"`, `"new-password"` on sign-up) (3.3.8).
- An action that cannot be undone (cancelling a registration, deleting an event) asks once, naming
  what will go.

## Speed on a phone

Readers open the site on a mobile network. A page should show its content within about 2.5 seconds
(LCP), not shift once shown (CLS under 0.1) and answer a tap within 200ms (INP) -- the Core Web
Vitals thresholds. In practice:

- Images carry `width` and `height`, and `loading="lazy"` below the fold.
- A heavy library (FullCalendar, Leaflet) loads only on the page that uses it.
- A script that fills in a label runs before the first paint, or the label's room is reserved.
