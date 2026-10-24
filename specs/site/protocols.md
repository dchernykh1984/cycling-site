# Site Specification: Results protocols

**Status**: Baseline -- describes the site as it works today
**Verified against**: `main` on 2026-10-24
**Code**: `protocols/` (models, views, `protocols/document.py`, `protocols/rendering.py`),
`protocols/static/protocols/`, `protocols/schema/protocol-document-v1.json`, `api/endpoints/protocols.py`
**Tests**: `protocols/tests.py`, `tests/test_protocol_images.py`, `tests/test_protocol_document.py`,
`tests/test_protocol_upload.py`, `tests/e2e/test_competition_result_emphasis.py`,
`tests/e2e/test_protocol_live.py`, `tests/e2e/test_protocol_document.py`, `api/tests.py`
(protocol endpoints)
**Related**: [events](events.md), [API](api.md); the `protocols` skill holds the security detail

## Overview

A protocol is what the timing software uploads through the API with the event's upload token: the
HTML file it writes for itself, a structured document describing the results (issue #310), or both
from one run. The event page links its protocols; each opens on a page of its own. A document is
drawn by the site, in its own look, for a phone and a desktop and in every skin; HTML alone is shown
as it was written, in a sandboxed frame. While results are live the page follows new uploads.

The document describes itself -- sections, columns with their labels, roles and priorities, cells,
header and footer lines, groups and column switches -- so a new column, header field or kind of
table needs a change in the generator only; the site knows nothing of laps, attempts or referees.

## User Scenarios

### Story 1 -- Publish results (P1)

1. **Given** the timing software holds the event's upload token, **When** it uploads an HTML file as
   the absolute or the group protocol (with an optional stage label and a live flag), **Then** the
   protocol is created or replaced and the call returns its id and the file's hash.
2. **Given** a second upload of the same type, **Then** the protocol is updated and the previous file
   kept as a version; the ten most recent versions are kept.
3. **Given** a delete call for a type, **Then** that protocol and its versions are removed and its
   link leaves the event page.
4. **Given** an upload with a structured document (`document`, JSON, schema 1), with or without the
   HTML, **Then** the protocol holds exactly what that upload carried -- the last upload wins in both
   directions -- and the call says which form is shown. A document that cannot be accepted is a 400
   alone; sent with HTML, the HTML is stored and `document_error` says why.
5. **Given** an upload that fails half-way (storage or database), **Then** the protocol keeps its
   previous content and file and nothing new is left on disk; uploads of one event take turns, so
   the protocol never mixes two uploads.

### Story 2 -- Read results (P1)

1. **Given** an event with protocols, **Then** its page links them as filled, bold buttons that stay
   legible in every skin, at rest, on hover and in focus; a live protocol is marked "Live".
2. **Given** a live protocol's page, **Then** it asks every minute whether a newer upload exists
   (`PROTOCOL_POLL_INTERVAL_MS`) and, when one does, loads it into a second, hidden frame; the frame
   reports which upload it holds, whether that upload is live and the form it is shown in, and only
   that report replaces the protocol on screen. A final upload ends the polling only once its own
   content is on screen; a final one shows the results without polling; the page lists the update
   history.
3. **Given** a newer upload that fails to load (an error page, a broken connection, a request that
   never answers, no report within `PROTOCOL_LOAD_TIMEOUT_MS`), **Then** the results already on screen stay, the page says the
   update failed, and the next round tries again -- final or not.
4. **Given** a hidden browser tab, **Then** it does not poll; on return it checks at once, and never
   runs two checks at the same time.
5. **Given** the protocol page, **Then** the fullscreen button has an accessible name, and a link
   opens the protocol on a page of its own (where a browser has no fullscreen for a frame, the
   button opens that page).

### Story 3 -- Read a drawn protocol on a phone (P1)

1. **Given** a phone, **Then** each table shows its main columns (place, number, name, result, or
   the document's priority 1; a table with none keeps its first three), the page never scrolls
   sideways, and a button on each row (keyboard-reachable) opens the columns that do not fit.
   Tablets show priority 1-2, desktops everything; "All columns" -- offered only where the short
   view leaves a column out -- shows every column, scrolling
   inside the table, with the place, number and name columns kept in view -- where they stay
   however often a filter or a switch is pressed while the table is scrolled. Group chips and
   column switches keep to one scrolling row on a phone; times stay on one line.
2. **Given** a reader, **Then** they search every field of a row -- name, number, team, city and
   the rest, not times or second lines -- in Latin or Cyrillic whichever the protocol uses (both
   are folded to one script, the rule the gallery's event picker uses), filter by the document's groups (in
   every table, whatever its layout), and switch the document's toggled columns; notes such as the
   reasons for a DSQ are always visible under their row. The group filter offers only groups that
   hold rows, and appears only when there are at least two of them; it is labelled "Category:" and
   its first chip, "All categories", shows every row.
3. **Given** a live drawn protocol, **Then** a newer upload swaps in its tables and keeps the reader's
   search, group and switches by their ids; a group that disappeared falls back to "All categories".
4. **Given** a protocol in another language than the page, **Then** the page says which.

### Edge Cases

- Unknown token: 401; no token: 422; an event not approved: 401; wrong protocol type, wrong content
  type, an over-size file or neither a file nor a document: 400; GET on the upload endpoint: 405.
- A protocol of an event that is not approved, hidden or deleted -- its page, its file, its fragment
  and its last-updated hash -- is 404; a protocol of an invite-only event is 404 to anyone not let in.

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
- **FR-PRO-007**: The document's schema is `protocols/document.py`, exported to
  `protocols/schema/protocol-document-v1.json` for the generators. Within a major version unknown
  fields are ignored, an unknown section type is drawn by its shape, an unknown role means none; an
  id used twice, a cell or a reference to something undeclared, a non-http(s) link, a NUL
  character (PostgreSQL cannot keep it) or JSON that cannot be read is refused.
- **FR-PRO-008**: A document may hold at most 100 000 table cells (rows x columns over every table,
  plus one per note), 200 columns and 5000 rows per table, 20 000 rows, 500 sections nested 3 deep.
- **FR-PRO-009**: HTML lines of a document are sanitized and keep only pictures from this site or
  inline (as FR-PRO-003); cell links are http(s), `nofollow noopener`.
- **FR-PRO-010**: `protocols/<pk>/fragment/` returns the drawn document with the hash, live flag and
  form of the row it was drawn from (`X-Protocol-*`); a protocol without a document answers empty.
- **FR-PRO-011**: A column with no heading and no value in any row is not drawn.

## Key Entities

- **Protocol**: event, type, HTML file and/or structured document, last updated, live flag, stage
  label, hash of the upload.
- **ProtocolVersion**: an earlier upload of a protocol, its file and/or document (ten kept).

## Local assumptions

- None known. A protocol document belongs to one language (`lang`), like a knowledge article: its
  labels are the referee's, not translated (an exception to constitution principle IV, recorded
  here).

## API gaps

- Reading results: an event's protocols, a protocol's document or HTML and its update history are
  served to browsers only; the API takes uploads.

## Open Questions

- Protocol generation is still done by a separate desktop application; moving it onto the site is
  open in issue #172.
