# Site Specification: News and the knowledge base

**Status**: Baseline -- describes the site as it works today
**Verified against**: `main` on 2026-10-21
**Code**: `news/`, `knowledge/` (models, views, forms), `cycling_site/richtext.py`
**Tests**: `news/tests.py`, `knowledge/tests.py`, `tests/test_article_meta.py`,
`tests/test_slug_ascii.py`, `tests/e2e/test_news_editor.py`, `tests/e2e/test_knowledge_editor.py`,
`tests/test_moderation_banner.py` (news submissions), `assistant/tests/test_chat.py` (the news chat)
**Related**: [site shell](site-shell.md) (search), [search visibility](search-visibility.md) (feeds,
sitemap), [API](api.md) (content endpoints); the `site-content` skill covers publishing on the live
site

## Overview

Two libraries of rich-text articles: news, each item carrying its title, intro and body in Russian,
Kazakh and English, with an optional cover image; and knowledge-base articles, each written in one
language (its locale) with a category and tags. Admins write and manage them directly; any confirmed
member may submit a draft for review; members comment.

## User Scenarios

### Story 1 -- Read (P1)

1. **Given** the news index, **Then** articles are listed newest first, a page at a time; an article
   page shows its title, cover, body and comments (author shown by full name when set, never by
   e-mail).
2. **Given** the knowledge index, **Then** articles are listed; an article is reached by an ASCII
   slug under the index; opened at another language's address, it is served in its own language
   with a banner saying so and a link to search.
3. **Given** search, **Then** news and knowledge articles are found by their text.

### Story 2 -- Write and manage (P1)

1. **Given** an admin, **Then** they create and edit articles on the site (not in the Wagtail admin)
   with a bundled Quill editor -- formatting, text colour, alignment, images with size and float. A
   news item is edited in a tab per language, and a server-side error opens the tab of the language
   that failed; a knowledge article is written in the one language chosen for it.
2. **Given** an admin, **Then** they may hide an article (404 for others, visible to admins), unhide
   it, delete it (soft), and set tags and category (knowledge).
3. **Given** an admin on a news item's add or edit page, **Then** the assistant's chat translates it,
   puts its formatting right and changes it as asked (see [event assistant](assistant.md)). A
   knowledge article is written by hand or through the API, and is not translated.

### Story 3 -- Submit a draft (P2)

1. **Given** a participant, **Then** they may submit a news item or a knowledge article; it waits as a
   draft submission.
2. **Given** an admin reviews it, **Then** approving creates the article (filling the columns of the
   language it was submitted in, sanitising its HTML) and rejecting records a note; a submission is
   approved or rejected once.
3. **Given** pending news, **Then** the news index shows a block with approve/reject actions to
   managers only, and the moderation banner counts the waiting submissions for admins.

### Story 4 -- Discuss (P3)

1. **Given** a participant, **Then** they may comment on a published article (empty bodies refused,
   line breaks kept); hidden articles take no comments (404).
2. **Given** an admin, **Then** they may delete comments.

### Edge Cases

- Articles are soft-deleted; a deleted comment is erased.
- Bodies are sanitised on every save, inline images kept; an over-long body is a translated form
  error, not a server error.
- Knowledge-article and Wagtail page slugs are ASCII even for a Cyrillic title; knowledge slugs are
  unique, within their maximum length, and never collide with the knowledge service URLs (submit,
  add, submissions, articles).
- A page's meta description is drawn from the article: the news intro first, else its body, flattened
  to prose and cut on a word.

## Functional Requirements

- **FR-ART-001**: Create, edit, hide, delete articles and moderate submissions: admin and up.
  Submit drafts and comment: participant and up.
- **FR-ART-002**: Rich text is sanitised (no scripts or dangerous attributes) and length-limited.
- **FR-ART-003**: Hidden or deleted articles are 404 for everyone but admins (hidden) and never
  syndicated or listed.

## Key Entities

- **NewsArticle**: title, intro, body per language, cover image, publisher, publication time, slug,
  hidden / deleted flags; **NewsArticleComment**.
- **KnowledgeArticle**: title, slug, locale, body, category, tags, publisher, publication and update
  times, hidden / deleted flags; **KnowledgeArticleComment**.
- **DraftSubmission**: a submitted news item or knowledge article, its status, reviewer and note.

## Local assumptions

- None known.

## API gaps

- Submitting news for review (participants; knowledge drafts already have their API).
- Commenting on news and knowledge articles.

## Open Questions

- The legacy Wagtail `NewsPage` (with its own comments and an auto-approve setting) still exists
  beside `NewsArticle`; whether any live page still uses it is not established here.
