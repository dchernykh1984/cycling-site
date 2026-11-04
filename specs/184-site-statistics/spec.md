# Feature Specification: The site's own statistics for its owners

**Feature Branch**: `184-site-statistics`
**Created**: 2026-11-04
**Status**: Implemented (pull request for issue #184)
**Input**: Issue #184 -- "add usage statistics": how many people use the site, how actively they move
around it, who signs up; collect it and show it somewhere. Discussed with the maintainer on
2026-11-04, who then asked for it to be built as Claude saw best; the site as built is
`specs/site/statistics.md`.

## Decisions

Taken with the maintainer on 2026-11-04:

1. **The owners only** see the statistics: a tab "Statistics" after "Virtual ride", shown to them
   alone, in the site's frame and in the two skins that draw their own menu (the menu item only, in
   the skin's own style).
2. **The team is counted apart.** The pages the owners and the admins open are their work, not
   readers' visits: they stay out of the people's numbers and show as the team's activity -- each
   member's pages and changes -- so the owners see how the other admins work.
3. **People and robots are told apart as Claude saw best**: a person's browser runs the page, whose
   own script (not a third party's) says it was opened; robots are counted on the server by their
   User-Agent, in kinds -- an AI assistant opening a page for a person, AI search, search engines,
   AI training, link previews, marketing services, monitoring, the site's own scripts, others.
4. **A read-only API**, for an owner's token: the maintainer first wanted the page alone, then agreed
   to the API so that Claude can read the numbers when given a token.
5. **Sums are kept for good**: a day's sums are a few hundred short rows; nothing about a visitor is
   stored.
6. **Periods**: today by the hour, a week, 30 days, 90 days, since the start of the year, a year, all
   time.
7. **"Who signs up"** in the issue is the list of members who joined in the period.
8. **The privacy policy** says how the site counts: it promised no analytics trackers and no
   third-party tracking code, which stays true; one paragraph describes the counting.

## User Scenarios & Testing

### User Story 1 - An owner sees how the site is used (Priority: P1)

1. **Given** an owner, **When** they open "Statistics", **Then** they see the period's people --
   visits, page views, pages per visit, a chart, where they came from, phones and computers,
   languages, popular pages -- then the robots, the team and what happened on the site.
2. **Given** any other member or a visitor, **Then** no tab, and the page is refused.

### User Story 2 - The numbers are honest (Priority: P1)

1. **Given** the owner reads many pages a day, **Then** none of them is a reader's view.
2. **Given** a robot that reads the site, **Then** it is counted among the robots, by kind, not
   among the people.

### User Story 3 - Claude reads the numbers (Priority: P2)

1. **Given** an owner's token, **Then** `GET /api/v1/stats/?period=` returns the page's numbers.

## Requirements

- **FR-001**: The statistics page and the API answer owners and superusers only (`SEE_SITE_STATS`).
- **FR-002**: The pages of members at `COUNTED_AS_TEAM` (admin) or above are the team's.
- **FR-003**: Only sums per day are stored; no address, cookie, identifier or whole User-Agent.
- **FR-004**: The day is the site's time zone, whatever zone a page was drawn in.
- **FR-005**: The counting cannot be made to store endless rows: keys are cut to 200 characters,
  and a day takes at most 500 new pages, referring sites and robot names each.
- **FR-006**: The page reads well at 360 px in every skin and every language; its charts have a
  table of the same numbers.

## Out of scope

- Unique visitors: with no cookie and no stored address they cannot be told honestly.
- Traffic before the counting starts: Cloudflare's and Search Console's own reports hold it.
