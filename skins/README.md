# Skins

Every folder here is a skin a reader can pick from the list behind the moon/sun button in the
navbar (and on their profile). A skin can change the whole look of the site, desktop and phone:
its colours and fonts, any rule of its stylesheet, and the markup itself -- any template of the
site can be replaced by the skin's own copy. Readers who did not pick the skin never see any of it.

`light` and `dark` are the site's own themes. They are also the two base modes every other skin
builds on, and they do not change without the maintainer (see "Checks" below).

## Starting a skin

```
.venv/bin/python manage.py startskin ubt --mode light
```

creates `skins/ubt/` with a manifest and an empty stylesheet, already valid. The folder name is the
skin's key: lowercase letters, digits and dashes, at most 32 characters. Profiles and cookies store
it, so **never rename a folder**. Deleting one is safe: whoever had picked it gets the default skin
(`DEFAULT_SKIN` in `cycling_site/settings/base.py`) until they pick again.

## What a skin is

```
skins/<key>/
    manifest.json   name in three languages, the mode it builds on, its place in the list
    skin.css        its stylesheet
    skin.js         optional: behaviour of its own
    templates/      optional: its own copies of the site's templates
    fonts/          optional: its font files and their licence
```

Only `manifest.json` and `skin.css` are required.

### manifest.json

```json
{
  "name": {"ru": "...", "kk": "...", "en": "..."},
  "mode": "light",
  "order": 30
}
```

- `name` -- shown in the list in the reader's language; all three are required. Write the Russian
  and Kazakh names as they read: the pre-commit hook rewrites them as `\uXXXX` escapes (the
  repository keeps json files ASCII), fails once, and the second commit goes through.
- `mode` -- `light` or `dark`: Bootstrap's colour mode for the page, and everything in
  `skins/<mode>/skin.css` applies before the skin's own stylesheet.
- `order` -- position in the list; light is 10, dark is 20.

### skin.css

Any CSS. It is on the page only while the skin is chosen, after Bootstrap (the Lux theme), the
site's stylesheet and the mode's stylesheet, so it wins any tie. Picking a skin of its own reloads
the page once to bring it in.

A skin on the dark mode can start from the variables the dark mode paints with; they are listed,
with what each paints, at the top of `skins/dark/skin.css`:

```css
:root[data-skin="<key>"] {
    --skin-accent: #fc6104;
    --skin-on-accent: #000;
}
```

### templates/

A file at `skins/<key>/templates/<path>` replaces the site's template at the same `<path>`, for
readers of this skin only. To change a page, find its template -- `cycling_site/templates/` holds
the shared ones (`base.html` is the frame of every page), each app keeps its own under
`<app>/templates/` -- copy it into the skin at the same path and edit the copy. What a template
can show is what its original uses; new data on a page is a change to the site's core, for the
maintainer.

Two things to keep in a copy:

- **The parts the site's tests work through.** The whole browser test suite runs in every skin
  (see "Checks"), so a button or a field it can no longer find fails it -- the failure names the
  missing element.
- **Translations.** Keep `{% trans %}` / `{% blocktrans %}` around the text; a new phrase needs its
  Russian and Kazakh in the translation catalogues, which is the maintainer's part.

When the maintainer later changes a template the skin has copied, the copy does not change with
it; the tests running in the skin show where it fell behind. A change that turns a skin's tests red
is not merged until the skin is green again: either its designers fix the skin, or the same pull
request fixes it.

### skin.js and fonts/

`skin.js` is loaded after the site's own script, only while the skin is chosen.

A font of the skin's own goes into `fonts/` with its licence (`LICENSE...` or `OFL.txt`), and its
`@font-face` family is named `skin-<key>-<role>` -- `skin-ubt-heading`, `skin-ubt-body` -- so two
skins never mean each other's font:

```css
@font-face {
    font-family: "skin-ubt-heading";
    src: url("fonts/heading.woff2") format("woff2");
}
```

## Looking at a skin locally

A database of its own, filled with sample events, news, registrations and accounts:

```
createdb skins_demo
export DATABASE_URL=postgres://localhost/skins_demo
.venv/bin/python manage.py migrate
.venv/bin/python manage.py shell < scripts/demo_seed.py
.venv/bin/python manage.py runserver
```

Then pick the skin from the list. Signed-in pages: sign in as `member_light@example.com` (a
participant) or `admin_light@example.com` (an admin), password `visual-pass-1`.

## Checks

On every pull request, and locally:

- `.venv/bin/python -m pytest tests/test_skins.py -n 0` -- every folder is a valid skin: manifest
  complete, key short enough, names escaped, fonts named for the skin, present and licensed.
- `E2E_SKIN=<key> .venv/bin/python -m pytest tests/e2e` -- the whole browser suite with the skin
  as everyone's starting skin, including `test_skin_contrast.py`: text at least 4.5:1 against what
  it is drawn on (3:1 for large text), at rest, under the pointer and in focus. CI runs this for
  every skin in its own job.
