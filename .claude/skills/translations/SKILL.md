---
name: translations
description: Three locales, gettext catalogues and the traps that silently swallow a translation in this repository. Read whenever a change adds or edits a user-visible string.
---

# Translations

`ru` (default), `kk`, `en`. Interface strings live in gettext catalogues under
`cycling_site/locale/<locale>/LC_MESSAGES/django.po`; content lives in per-locale model columns.

## Data fields

Localize reader-facing names, titles, captions and descriptions by default: non-page models use
django-modeltranslation with ru / kk / en columns, and forms and administration expose each one.
Preserve existing text in a data migration; read the active locale with the site's fallback and
write the actual locale columns so a fallback is never copied into an empty translation.
A document such as a knowledge article may instead belong to one locale and be listed only in
that locale. IDs, dates, numbers and URLs are not translated. Record any other exception in the
area's specification. A new field's review checks display, editing, migration and empty locales.

## Adding a string

1. Wrap it: `{% trans "..." %}` in templates, `gettext` / `gettext_lazy` in Python. Source strings
   are English -- the repository is ASCII-only.
2. `.venv/bin/python manage.py makemessages -l ru -l kk --no-obsolete`
3. Fill in `msgstr` for both catalogues.
4. `.venv/bin/python manage.py compilemessages`
5. Commit the `.po` **and** the `.mo`.

## The traps

- **Fuzzy entries are ignored at runtime.** `makemessages` marks a changed string fuzzy and keeps
  the old translation next to it; gettext then serves the English source. Clear the flag whenever
  you touch an entry (`entry.flags.remove("fuzzy")` if you edit catalogues with `polib`).
- **Never put non-ASCII in source files.** A pre-commit hook rejects python, markdown, yaml, toml,
  shell and json containing it, and ruff flags Cyrillic letters that look like Latin ones. Assert
  against `gettext("...")` under `translation_override` in tests rather than pasting the Russian.
  Where a Cyrillic constant is unavoidable in code, build it from code points and say why.
- **The URL decides the language**, not the browser: `/ru/`, `/kk/`, `/en/`. A test that wants the
  English page must request the English address -- `HTTP_ACCEPT_LANGUAGE` no longer changes
  anything. `tests/language_urls.in_language(url, "en")` does the rewriting.
- **The active language leaks between tests.** A root `conftest.py` fixture resets it; when a test
  queries a modeltranslation field (`name`, not `name_ru`) it is reading whatever language is
  active, which is a common source of confusing failures.
- **Kazakh letters, not their look-alikes.** Write Kazakh with its own letters: a plain Russian
  "k" for "q", "n" for "ng", "u" for "u-straight", or a Latin "i" for the Kazakh one, is a misspelling
  a Kazakh reader sees at once ("Shygu" for log out was one). `tests/test_catalogues.py` checks every
  catalogue for a Latin letter inside a Cyrillic word, a letter typed three times, and a lost
  placeholder or tag; `tests/test_kazakh_catalogue.py` pins the words already put right.
- **One word for one thing.** The Russian catalogue calls an event "meropriyatie" and the Kazakh one
  "is-shara"; a region is "aimaq" in Kazakh. The catalogue checks guard both.
