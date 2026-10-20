# Skins

Every folder here is a skin a reader can pick from the list behind the moon/sun button in the
navbar (and on their profile). The folder name is the skin's key: profiles and cookies store it, so
**never rename a folder**. Deleting one is safe -- whoever had picked it gets the default skin
(`DEFAULT_SKIN` in `cycling_site/settings/base.py`, the light one) until they pick again.

`light` and `dark` are the site's own themes and the two base modes every other skin builds on.

## What a skin is

```
skins/<key>/
    manifest.json   name in three languages, the mode it builds on, its place in the list
    skin.css        what it changes
```

`manifest.json`:

```json
{
  "name": {"ru": "...", "kk": "...", "en": "..."},
  "mode": "dark",
  "order": 30
}
```

- `name` -- shown in the list in the reader's language; all three are required. Write the Russian
  and Kazakh names as they read: the pre-commit hook rewrites them as `\uXXXX` escapes (the
  repository keeps json files ASCII), fails once, and the second commit goes through.
- `mode` -- `light` or `dark`. The page gets Bootstrap's colour mode and everything in
  `skins/<mode>/skin.css`; the skin then changes only what it means to.
- `order` -- position in the list; light is 10, dark is 20.

`skin.css` holds the skin's own values under its own key:

```css
:root[data-skin="<key>"] {
    --skin-accent: #fc6104;
    --skin-on-accent: #fff;
}
```

The variables the dark mode paints with, and what each of them paints, are listed at the top of
`skins/dark/skin.css`. Bootstrap's page-wide variables (`--bs-body-bg`, `--bs-body-color`, ...) can
be set the same way; the Lux theme paints buttons with fixed colours, so a skin cannot recolour them
yet -- more variables (buttons, fonts, the skin's own templates) come with the next step of #324.

A skin's stylesheet is on the page only while that skin is chosen, so picking it from the list
reloads the page once.

## Checking a skin

- `.venv/bin/python -m pytest tests/test_skins.py -n 0` -- every folder loads: manifest complete,
  mode valid, `skin.css` present, names escaped.
- `.venv/bin/python tests/visual/run.py` -- screenshots of the branch against `origin/main` in the
  light and dark themes; any pixel that moved fails. CI runs the same check on every pull request
  ("Light and dark unchanged"); a deliberate change to light or dark goes through only with the
  `visual-change-approved` label, which the maintainer sets.
