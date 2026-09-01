---
name: site-content
description: Publishing and editing what readers see - knowledge articles, news and events - on the live site. Covers the admin API, the three locales, images, and the traps in the markup.
---

# Site content

Three kinds of content: **knowledge articles** (`/knowledge/`), **news** (`/news/`) and **events**
(`/calendar/`). All are edited on the site by people; you edit them through the API or the ORM when
the maintainer asks.

## Publishing through the API as an administrator

The admin token belongs to a user, not to the environment, so read it on the instance rather than
carrying it around:

```python
admin = User.objects.filter(role__in=[User.Role.OWNER, User.Role.ADMIN]).exclude(api_token=None).first()
requests.post(url, json=payload, headers={"Authorization": f"Bearer {admin.api_token}"})
```

Run that from the production shell (see `production-access`) so the token never leaves the box.

- `POST /api/v1/knowledge/` -- one article per locale, each with its own slug and URL.
- `PATCH /api/v1/knowledge/{id}` -- partial update; send only what changes.
- `POST /api/v1/news/` and `/api/v1/competitions/` follow the same shape.

## Three locales, every time

Everything a reader sees exists in **ru, kk and en**. Knowledge articles are three separate rows,
one per locale. Events and news carry `_ru` / `_kk` / `_en` columns on one row. Publishing only
Russian leaves two thirds of the site empty, and the language a reader gets is decided by the URL
prefix, not by their browser.

Translate faithfully rather than transliterating, and keep the same structure in all three.

## Body markup

The body is sanitized on save. Surviving tags: `p, br, hr, blockquote, h2, h3, h4, ul, ol, li,
strong, b, em, i, u, s, sub, sup, span, code, pre, a, table, thead, tbody, tr, th, td` -- plus `img`
with an http(s) or data source.

- `h1` is the page title, so sections start at `h2`.
- Paragraphs are `<p>`; stripping them and relying on `<br>` collapses the text into one block.
- Django templates do not support multi-line `{# #}` comments -- use `{% comment %}` (there is a
  test that enforces this).

## Images

Upload the file to `/var/media/<folder>/` (see `production-access`) and reference it as
`https://universalbicycle.team/media/<folder>/<name>.jpg`. Downscale to about 1000 px first.

Give every `<img>` `width` and `height` attributes: without them the browser cannot reserve space
before the file arrives, and in an embedded protocol the iframe measures the page too short.

Only use photographs you are allowed to publish. Wikimedia Commons under CC BY-SA works if the
caption names the author, the licence and links to the file page; product shots from a shop's
website do not. When nothing suitable exists, say so and ask the maintainer for their own photo
rather than substituting a lookalike.

Instagram is never named, linked, or used as an image source anywhere on the site.

## Categories and slugs

The knowledge category is free text, not a vocabulary: the filter chips are simply the strings
somebody typed. Current set, per locale:

Four exist today, each with a spelling per locale: **Tools** (software), **Equipment**
(hardware), **Refereeing** and **Training**. This file is ASCII, so the Russian and Kazakh spellings
are not reproduced here -- read them off an existing article in that locale and copy them character
for character, or a duplicate chip appears next to the real one.

Slugs are generated from the title, and a Cyrillic-only title yields `article-N` because the
generator is ASCII-only. That is existing behaviour, not a fault of your publish -- mention it, do
not silently invent a different scheme.

## Events

An event's body carries a short description only: the start point belongs in the location, the
categories and the sport in their own structured fields. When a source announcement contradicts
itself, transcribe what it says and flag the contradiction to the maintainer instead of resolving it
yourself.
