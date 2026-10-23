# Site Specification: Results protocols

**Status**: Baseline -- describes the site as it works today
**Verified against**: `main` on 2026-10-23
**Code**: `protocols/` (models, views), `protocols/static/protocols/protocol-live.js`, `api/endpoints/protocols.py`
**Tests**: `protocols/tests.py`, `tests/test_protocol_images.py`,
`tests/e2e/test_competition_result_emphasis.py`, `tests/e2e/test_protocol_live.py`, `api/tests.py`
(protocol endpoints)
**Related**: [events](events.md), [API](api.md); the `protocols` skill holds the security detail

## Overview

A protocol is an HTML results file made by the timing software and uploaded through the API with
the event's upload token. The event page links its protocols; each opens on a page of its own that
shows the file in a sandboxed frame and, while results are live, refreshes it as new uploads
arrive.

## User Scenarios

### Story 1 -- Publish results (P1)

1. **Given** the timing software holds the event's upload token, **When** it uploads an HTML file as
   the absolute or the group protocol (with an optional stage label and a live flag), **Then** the
   protocol is created or replaced and the call returns its id and the file's hash.
2. **Given** a second upload of the same type, **Then** the protocol is updated and the previous file
   kept as a version; the ten most recent versions are kept.
3. **Given** a delete call for a type, **Then** that protocol and its versions are removed and its
   link leaves the event page.

### Story 2 -- Read results (P1)

1. **Given** an event with protocols, **Then** its page links them as filled, bold buttons that stay
   legible in every skin, at rest, on hover and in focus; a live protocol is marked "Live".
2. **Given** a live protocol's page, **Then** it asks every minute whether a newer upload exists
   (`PROTOCOL_POLL_INTERVAL_MS`) and, when one does, loads it into a second, hidden frame; the frame
   reports which upload it holds, whether that upload is live and the form it is shown in, and only
   that report replaces the protocol on screen. A final upload ends the polling only once its own
   content is on screen; a final one shows the results without polling; the page lists the update
   history.
3. **Given** a newer upload that fails to load (an error page, a broken connection, no report within
   `PROTOCOL_LOAD_TIMEOUT_MS`), **Then** the results already on screen stay, the page says the
   update failed, and the next round tries again -- final or not.
4. **Given** a hidden browser tab, **Then** it does not poll; on return it checks at once, and never
   runs two checks at the same time.
5. **Given** the protocol page, **Then** the fullscreen button has an accessible name, and a link
   opens the protocol on a page of its own (where a browser has no fullscreen for a frame, the
   button opens that page).

### Edge Cases

- Unknown token: 401; no token: 422; an event not approved: 401; wrong protocol type, wrong content
  type or an over-size file: 400; GET on the upload endpoint: 405.
- A protocol of an event that is not approved, hidden or deleted -- its page, its file and its
  last-updated hash -- is 404; a protocol of an invite-only event is 404 to anyone not let in.

## Functional Requirements

- **FR-PRO-001**: Protocol types: absolute and group, one of each per event (with a stage label).
- **FR-PRO-002**: The protocol file is served as HTML with `nosniff`, `no-store`, `X-Frame-Options:
  SAMEORIGIN` and a narrow Content Security Policy: `sandbox allow-scripts` without same-origin,
  inline script and style only, no frames, forms or connections; external script, `<base>` and
  meta-refresh are stripped.
- **FR-PRO-003**: Images in a protocol may come only inline (`data:`) or from the serving site's own
  address (and the media host, when media is kept elsewhere); the address is taken from the
  deployment, not written down; nothing else is reachable.
- **FR-PRO-004**: The polling address carries the reader's language prefix like every reader-facing
  address.
- **FR-PRO-005**: The live page trusts only the state read with the content it applies: the framed
  file carries the hash, the live flag and the form of the row it was read from, so an upload that
  lands between the check and the load can neither be shown under another upload's flag nor end
  live early. Content in another form than the page reloads the page.
- **FR-PRO-006**: The protocol page's link preview title is "<event> -- <kind of protocol>".

## Key Entities

- **Protocol**: event, type, HTML file, last updated, live flag, stage label.
- **ProtocolVersion**: an earlier file of a protocol (ten kept).

## Local assumptions

- None known.

## Open Questions

- Protocol generation is still done by a separate desktop application; moving it onto the site is
  open in issue #172.
