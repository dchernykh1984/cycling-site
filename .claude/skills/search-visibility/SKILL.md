---
name: search-visibility
description: How this site is made findable - per-language URLs, canonical and hreflang, the sitemap sections, structured data, feeds and IndexNow. Read before touching URLs, templates' head, or anything a crawler reads.
---

# Search visibility

The site was invisible to search engines until this was built; the pieces below hold each other up,
so changing one without the others usually breaks the arrangement.

## One address per language

Every reader-facing URL carries a prefix: `/ru/...`, `/kk/...`, `/en/...` (`i18n_patterns` with
`prefix_default_language=True`). Machine-facing addresses -- `/api/v1/`, both admins, `/media/`,
`/documents/`, `/i18n/`, `sitemap.xml`, `robots.txt`, the IndexNow key file -- carry none.

- The **prefix decides the language**, not the cookie, not `Accept-Language`, not the profile: one
  address must not answer differently to different readers. `LocaleFallbackMiddleware` applies the
  stored preference only when the path has no prefix.
- An **unprefixed URL 302s** to the prefix matching the reader (cookie, then `Accept-Language`), so
  a link pasted into a chat still opens in each reader's own language.
- `SiteLocaleMiddleware` suppresses that redirect for the machine-facing prefixes: a missing API
  address answers 404 rather than touring the site.
- Share short links with people (`/calendar/533/`), prefixed ones only when you mean that language.

## What every page carries

`base.html` builds: a per-page `<title>` and `meta description` (from `meta_title` /
`meta_description` in the view's context, with a site-wide fallback), a self-canonical, `hreflang`
alternates for all three languages plus `x-default`, Open Graph and Twitter tags, and the feed
`<link rel="alternate">`s. A view that can describe its page should set those two context keys --
`calendar_app/listing_seo.py` does it for a filtered calendar, which is what makes
`?location=<id>` a page about a city rather than a copy of the calendar.

Structured data: `SportsEvent` on an event (`calendar_app/seo.py`), `Article` / `NewsArticle` on
knowledge and news (`cycling_site/summaries.py`). Both are escaped so a title containing `</script>`
cannot break out.

## Sitemap

`sitemap.xml` is an **index**, generated per request from the database -- there is nothing to
rebuild and no hook to fire when something is published. Sections: `wagtail`, `knowledge`, `news`,
`competitions` (paged at 500) and `calendar-filters` (the city and discipline pages worth
indexing). Each section is `i18n = True` with `alternates` and `x_default`, so every entry appears
once per language with links to its translations.

## Feeds

`/calendar/calendar.ics` honours the same filters as the list view (`text/calendar`, folded at 75
octets, all-day events ending the day after the last one). `/news/rss.xml`, `/news/atom.xml`,
`/calendar/events.rss`, `/calendar/events.atom` -- news, and events by approval date.

## Telling engines about a new page

The classic sitemap pings are dead (Google's endpoint 404s, Bing's 410s). **IndexNow** is what
works, and Yandex honours it, which matters for this audience. `cycling_site/indexnow.py` submits a
published page in all three languages, wired to `post_save` so it fires whichever door the page came
through -- moderation screen, admin, or the API an agent posts to. It needs `INDEXNOW_KEY` set; the
site serves that key at `/<key>.txt`, which is how the engines verify the host.

Google has no equivalent: for Google it is the sitemap, internal linking, and patience. Both
consoles (Search Console, Yandex Webmaster) are the maintainer's to check -- you cannot query index
status from a script, search engines block it.

## After a deploy that touches this

Verify with a Googlebot user agent: `sitemap.xml` answers 200 and lists its sections, a section
file is non-empty, an unprefixed page 302s to a prefixed one, an event page carries canonical,
three hreflang links and its JSON-LD, and the key file returns the key.
