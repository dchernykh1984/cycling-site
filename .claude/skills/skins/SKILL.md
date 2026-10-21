---
name: skins
description: How the site's look is split into skins (issue #324) - the untouchable light and dark themes, designers' skins with their own CSS, script, fonts and templates, the checks that guard them, and what to do when a change to the site breaks a skin. Read before touching anything a reader sees, and before working inside skins/.
---

# Skins

The site's look lives in `skins/`, one folder per skin. The designer's guide is `skins/README.md`;
this file is what an agent needs on top of it.

## Who owns what

- **`skins/light` and `skins/dark` are the maintainer's.** They like them as they are. Their
  colours, their rules, and anything shared that changes how they look (`cycling_site.css`, a
  shared template, Bootstrap/Lux) do not change without the maintainer asking for it.
- **Every other folder belongs to the designers who made it.** Their markup, CSS and script are
  theirs to shape. Touch a designer's skin only to keep it working after a change to the site
  (below), and keep such a fix in a commit of its own.

## How a skin works

- `cycling_site/skins.py` reads every `skins/<key>/manifest.json` once (`registry()`). The key is
  the folder name: profiles (`User.theme`, 32 characters) and the guest's `skin` cookie store it,
  so a folder is never renamed. An unknown key falls back to `DEFAULT_SKIN` without being
  overwritten.
- `light` and `dark` are the base modes: their stylesheets are always on the page and switching
  between them needs no reload. Every other skin builds on one of them (`"mode"`), and its
  stylesheet, `skin.js` and templates are on the page only while it is chosen; entering or leaving
  it reloads the page.
- A skin's own templates (`skins/<key>/templates/<path>`) replace the site's template at the same
  path for that skin's readers: `SkinMiddleware` puts the skin into a context variable,
  `SkinLoader` reads its folder first, `SkinCachedLoader` keeps one cached copy per skin. A
  template rendered outside a request (e-mails) is always the site's own.
- Fonts in a skin are named `skin-<key>-<role>` and sit in `fonts/` with their licence; the
  registry refuses the folder otherwise. `manage.py startskin <key> --mode light|dark` lays out a
  valid new skin.

## When a change to the site touches a skin

A skin that copied a template does not get later changes to it. So when you change a template, a
view's context or anything the browser tests rely on:

1. `grep -rl "<the template's path>" skins/*/templates` -- does any skin carry its own copy?
2. Run the browser suite in every skin, not only light: `E2E_SKIN=<key> .venv/bin/python -m
   pytest tests/e2e -n 8` for each folder under `skins/` (CI does the same in the
   `e2e-skin (<key>)` jobs).
3. A skin that goes red holds the pull request: it does not merge until the skin is green. Either
   the skin's designers fix it, or you fix `skins/<key>/` in a commit of its own in the same pull
   request -- bringing the new part of the page into their copy, in their markup, not replacing
   their design with the site's.
4. A new phrase in a template needs its Russian and Kazakh in the catalogues (the `translations`
   skill), whether the template is the site's or a skin's.

## Checks and tools

- `tests/test_skins.py`, `tests/test_skin_templates.py`, `tests/test_startskin.py` -- the registry,
  template overrides, the folder layout.
- `tests/e2e/test_skin_contrast.py` -- text at least 4.5:1 (3:1 large) at rest, hover and focus,
  in the skin the suite runs in. `KNOWN_SHORTFALLS` records where light and dark already fall
  short; they are kept, not fixed, and a designer's skin gets no such allowance. The helper
  (`tests/e2e/contrast.py`) reads colours as drawn and refuses filters, blend modes and background
  images rather than guess.
- `tests/skin_fixtures.py` -- `trial_skin()` builds a throwaway skin in a temporary folder for
  tests; no sample skin is committed, since it would appear in every reader's list.
- A local database to look at a skin in: `skins/README.md`, "Looking at a skin locally".
