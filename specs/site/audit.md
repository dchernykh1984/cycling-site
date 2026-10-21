# Site Specification: The audit log

**Status**: Baseline -- describes the site as it works today
**Verified against**: `main` on 2026-10-21
**Code**: `audit/` (models, signals, middleware, views, Wagtail hooks)
**Tests**: `audit/tests.py`
**Related**: [events](events.md), [news and knowledge](news-and-knowledge.md),
[registrations](registrations.md), [API](api.md)

## Overview

Every create, update and delete of the site's main content is recorded with who did it and when,
whether it came through the site, the admin or the API.

## User Scenarios

### Story 1 -- See who changed what (P2)

1. **Given** an event, a news article, a knowledge article or draft, or a registration is created,
   updated (including a soft delete) or deleted, **Then** an entry records the time, the member, the
   action, the object's type, id and name, and the fields saved when the save named them.
2. **Given** a superuser, **Then** the log is listed in the admin, newest first; nobody else sees it.

### Edge Cases

- A change made through the API is attributed to the token's member (the API authentication keeps
  the audit middleware's current user in step).
- A change with no signed-in member (a migration, a management command) is recorded without a user.

## Functional Requirements

- **FR-AUD-001**: Watched models: Competition, KnowledgeArticle, DraftSubmission, NewsArticle,
  NewsPage, CompetitionRegistration.
- **FR-AUD-002**: Actions: created, updated, deleted.

## Key Entities

- **AuditLog**: timestamp, user (kept null when the user is removed), action, object type, id,
  representation, changed fields.

## Local assumptions

- None known.

## Open Questions

- Locations, users' roles and comments are not audited; whether they should be is undecided.
