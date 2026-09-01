---
name: translations
description: Three locales, gettext catalogues and the traps that silently swallow a translation in this repository. Read whenever a change adds or edits a user-visible string.
---

# Translations

`ru` (default), `kk`, `en`. Interface strings live in gettext catalogues under
`cycling_site/locale/<locale>/LC_MESSAGES/django.po`; content lives in per-locale model columns.

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
