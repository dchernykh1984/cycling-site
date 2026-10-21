# Site Specification: Skins (the look of the site)

**Status**: Baseline -- describes the site as it works today
**Verified against**: `main` on 2026-10-21
**Code**: `skins/`, `cycling_site/skins.py`, `cycling_site/templates/_skin_select.html`,
`cycling_site/static/js/cycling_site.js`, `home/management/commands/startskin.py`,
`scripts/demo_seed.py`
**Tests**: `tests/test_skins.py`, `tests/test_skin_choice.py`, `tests/test_skin_templates.py`,
`tests/test_startskin.py`, `tests/e2e/test_theme_choice.py`, `test_skin_of_its_own.py`,
`test_skin_contrast.py`, `test_contrast_helper.py`; CI `e2e-skin` jobs
**Related**: [accounts](accounts.md), [site shell](site-shell.md); `skins/README.md` for designers and
the `skins` skill for agents (issue #324)

## Overview

The look of the site is a skin, one folder each under `skins/`. Light and dark are the site's own
and the two base modes; designers add skins of their own -- any CSS, a script, fonts, their own
copies of any template -- without touching the site's code. A reader picks a skin from the list
behind the moon/sun button.

## User Scenarios

### Story 1 -- Pick a look (P1)

1. **Given** the button in the navbar (or on the profile), **Then** it shows the mode the page is in
   -- a moon in a dark skin, a sun in a light one -- and opens the list of all skins, named in the
   reader's language; on a phone the list opens to the right of the button and stays on screen.
2. **Given** a reader switches between light and dark, **Then** the page changes in place; going into
   or out of any other skin reloads the page once saved.
3. **Given** a member, **Then** the choice is kept in their profile; **given** a guest, in a `skin`
   cookie (an old choice left in the browser's storage is carried over on the first visit).
4. **Given** a key no folder answers to any more, **Then** the page is drawn in `DEFAULT_SKIN`
   (light) and the stored choice is left as it is.

### Story 2 -- A designer adds a skin (P1)

1. **Given** `manage.py startskin <key> --mode light|dark`, **Then** a valid skin folder is laid out.
2. **Given** a skin's `templates/<path>`, **Then** it replaces the site's template at that path for
   that skin's readers only; the template cache keeps one copy per skin, and `runserver` picks up an
   edit without a restart.
3. **Given** a skin's `skin.css` and `skin.js`, **Then** they are on the page only while it is chosen.

### Story 3 -- Nothing breaks unnoticed (P1)

1. **Given** every skin but light, **Then** the whole browser suite runs again with it as the
   starting skin, including the contrast check; a change that turns a skin red does not merge until
   the skin is green again.

### Edge Cases

- Fonts of a skin are named `skin-<key>-<role>`, present in `fonts/` and licensed, or the registry
  refuses the folder.
- A skin's key is at most 32 characters (the profile field); the manifest's ru/kk/en names are
  stored as ASCII escapes by a pre-commit hook.
- Contrast is judged as drawn: colours of any format, transparency and opacity blended over what
  lies beneath; filters, blend modes and background images under text are refused, not guessed.

## Functional Requirements

- **FR-SKN-001**: A skin is `skins/<key>/manifest.json` (names in the site's languages, base mode,
  order) and `skin.css`; optional `skin.js`, `templates/`, `fonts/`.
- **FR-SKN-002**: Light and dark stylesheets are always on the page; a designer's skin adds its own
  after them only while chosen.
- **FR-SKN-003**: Text in a designer's skin is at least 4.5:1 against what it is drawn on (3:1 for
  large text) at rest, under the pointer and in focus; light and dark keep their recorded shortfalls
  as floors.

## Key Entities

- **Skin** (from the registry): key, mode, order, names, whether it has a script.
- **User.theme** / the `skin` cookie: the chosen key.

## Local assumptions

- **Accepted** (maintainer, 2026-10-21: the three languages are deliberate and a fourth is not planned -- it would mean translating every event and article, beside which naming the three in code costs nothing). A manifest must name its skin in exactly Russian, Kazakh and English: the list is a constant in
  `cycling_site/skins.py` (`LANGUAGES`), not the site's `LANGUAGES` setting.

## Open Questions

- None known.
