# Feature Specification: Event photos from portable indexed albums

**Feature Branch**: `349-external-photo-albums`
**Created**: 2026-10-25
**Status**: Draft for maintainer review; no application implementation in this change
**Issue**: [#349](https://github.com/dchernykh1984/cycling-site/issues/349)
**Input**: External storage, portable photo indexes, event and personal galleries.
StartProtocolMaker is the primary source of issued bibs. Reuse known facts; explain preparation
where it is required. Pilot on historical events 533 (Google Drive) and 719 (Dropbox), with room
for a third event.

## User Scenarios & Testing

### User Story 1 - Make existing race albums searchable (Priority: P1)

An event manager connects several existing albums to an old event, prepares indexes on a local
computer and publishes indexed photos. Originals stay where they are. A reader opens the event,
searches a bib and downloads photos even when account matching is not ready.

**Why this priority**: The first useful release must work on existing events, without waiting for
another race or requiring a replacement storage subscription. The named pilot sources are event
533 on Google Drive and event 719 on Dropbox, as supplied by the maintainer; inspect them later.

**Independent Test**: Connect two photographers' albums to one historical event; import their
indexes; find a bib across both albums with storage access disabled for metadata search.

**Acceptance Scenarios**:

1. **Given** existing Dropbox albums, **When** their manager connects and indexes them, **Then**
   the event shows searchable previews and original downloads without copying originals to the site.
2. **Given** a partially indexed album, **Then** readers see available results and progress;
   an unprocessed photo is not reported as containing no riders.
3. **Given** several albums at one event, **Then** one search covers them and retains each
   photographer's credit, source and download information.
4. **Given** known historical bibs but no account association, **Then** bib search works; personal
   pages explain the missing association without requiring new registrations for an old race.
5. **Given** an event with photo links in additional materials, **Then** indexed albums have a
   separate event-page section with indexing/search status; additional materials retain videos,
   clips, documents and other links. A link is moved only after a working album is confirmed.

### User Story 2 - Understand and connect an album (Priority: P1)

The manager sees what the site supports beside the album-link input, before granting access.
Instructions do not require a development ticket or private advice from the maintainer.

**Independent Test**: A first-time manager uses only the connection page and linked guide to
prepare an accepted index and diagnose an unsupported link or invalid index.

**Acceptance Scenarios**:

1. **Given** the album-link field, **Then** adjacent help lists enabled services, required access,
   accepted index versions, a downloadable example and preparation instructions.
2. **Given** local indexing, **Then** the guide covers installation, folder selection, running and
   resuming indexing, reviewing uncertain bibs, publishing previews/index and refreshing the site.
   Supported operating systems, processing location and known limits are explicit.
3. **Given** an unsupported service, missing index, ambiguous path, expired access or throttling,
   **Then** the page names the cause and next action while retaining entered values.
4. **Given** read-only access, **Then** the page explains that import works but upload through the
   site does not; planned services are not labelled supported.

### User Story 3 - See my photos without entering my bib again (Priority: P1)

A participant opens "My photos at this event" or their photos across registrations. The site uses
issued bibs from StartProtocolMaker, not numbers computed from participant-list positions.

**Independent Test**: Preserve a registration reference through offline import, assignment,
editing, save/restart and upload; the athlete's gallery finds the assigned bib's photos.

**Acceptance Scenarios**:

1. **Given** a registration linked to the athlete's account, **When** StartProtocolMaker returns
   its bib, **Then** event and cross-event galleries use it without another bib input.
2. **Given** a corrected bib, **Then** accepted correction changes personal results and retains
   provenance; conflicting assignments are visible to the manager and do not guess a winner.
3. **Given** an account that entered someone else, **Then** those photos are not automatically
   labelled as the account holder's own photos.
4. **Given** old start lists/results, **Then** a manager reviews suggested registration matches
   once and retains confirmed associations. Name equality alone never establishes identity.

### User Story 4 - Download selected photos or all my photos (Priority: P2)

A reader downloads selected photos, all matches at one event or personal matches grouped by event.
Archive preparation shows progress, limits, expiry and unavailable files.

**Independent Test**: Request an archive across two albums with one unavailable original; report
successful and failed files and allow retry without repeating the selection.

### User Story 5 - Change storage without changing the gallery (Priority: P2)

A manager uses Google Drive or Dropbox through the same workflow. Another service needs a connector,
not service-specific rules in search or personal pages.

**Independent Test**: Import one portable album through two adapters; stable photo identities,
number matches and access rules survive a verified source move.

### Edge Cases

- Several people/bibs in one photo; unreadable, uncertain or falsely recognized digits; leading zeroes.
- Reused bibs across races; equal names; relays; multiple entries; cancellation after the race;
  an on-the-day entrant missing from online registrations.
- Expired access, removed sharing, duplicate filenames, moved files, out-of-order indexes,
  interrupted import and concurrent managers.
- Public originals remain public at their provider independently of the site's visibility setting.

## Requirements

### Functional Requirements

- **FR-001**: Read external albums through a common connector interface, initially Dropbox and
  Google Drive. Other services, including Yandex Disk, need an adapter and shared conformance
  checks. Unsupported adapters must not appear as working options.
- **FR-002**: Accept a documented, versioned, storage-independent index beside the photos. Each
  photo has a stable identity, original/preview references and zero or more bib observations, with
  explicit processing state and correction provenance. Originals are not rewritten.
- **FR-003**: Import validated indexes into a durable site search index. Event, bib and personal
  metadata searches use it without contacting photo storage; retrieving media is separate.
- **FR-004**: Publish revisions atomically, resume interrupted work and make repeat imports
  idempotent. Failed replacements retain the last valid index. Progressive processing shows counts
  and never silently removes photos missing from a partial run.
- **FR-005**: Provide a documented local CPU indexing path producing the portable format, with
  resumable processing and review of uncertain bibs. Recognition runs outside page requests.
  Optional later server recognition produces the same format and is not a prerequisite.
- **FR-006**: Beside the album input explain services, access, index versions/example and local
  preparation. Help and validation share capability/version definitions. Explain processing
  location, external visibility, material costs/limits, failures and the next action.
- **FR-007**: Allow event managers to connect/manage their event's external albums. Retain existing
  curated albums, originals and their current administration rights.
- **FR-008**: Offer event-level bib search across albums, personal event photos and a cross-event
  personal gallery. Personal association requires a confirmed athlete-registration-bib link;
  manual event-level bib search works without such a link.
- **FR-009**: StartProtocolMaker authors issued bib assignments. Preserve registration references
  through imports, edits, local persistence, restart and exchange; return them with actual bibs.
  Do not ask the participant to supply the same fact again.
- **FR-010**: Backfill historical numbers from retained start lists/results with a preview of
  candidate matches and manager confirmation. Retain source and reviewer. Missing identities stay
  unresolved; do not create accounts, registrations or personal links from name equality.
- **FR-011**: Keep legacy timing exchange working. Add structured identity/bib metadata without
  repurposing comments, changing positional records or interpreting a bib as a person ID. Define
  outcomes for duplicate assignments, reassignment, stale devices and offline retries.
- **FR-012**: Offer individual and bounded asynchronous bulk downloads with progress, expiry,
  cancellation and unavailable-file reports. Recheck access when delivering files.
- **FR-013**: Apply event/album visibility and ownership to pages, search, previews, API and archives;
  non-visible resources answer 404. Keep credentials and private registration facts out of portable
  indexes. Explain that hiding a site page cannot make public provider links private.
- **FR-014**: Ship participant/organizer operations through `/api/v1/` with page-equivalent
  permissions and localized fields. Help and reader-facing fields support ru/kk/en, phones,
  keyboard and screen readers.
- **FR-015**: Reuse known event, account and connection facts with permission; prefill editable
  values and keep values after recoverable errors. Registering others does not confer their identity.
  Corrections ask for a decision, not for repeated profile entry.
- **FR-016**: Provide disconnection, resync, correction and removal with explicit effects. Removing
  a site connection does not erase external originals. Access failure never broadens permissions
  or publishes a private file.

- **FR-017**: Present indexed participant-photo albums in a separate event-page section. Keep
  additional materials for videos, clips, documents and other resources. Existing photo links stay
  usable until their indexed replacement is confirmed; moving one preserves its original source
  and is an explicit manager action, not destructive rewriting of the event description.

### Key Entities

- **Storage connection / external album**: provider access, bounded root, event, localized title
  and credit, visibility and capabilities.
- **Index revision / photo / bib observation**: snapshot, portable identity, asset references,
  recognition state, candidates and reviewed corrections.
- **Issued bib assignment / historical match**: event, registration or unresolved entrant, number,
  source, revision and confirmation/conflict/revocation history.
- **Import / archive job**: owner, bounded selection, progress, retry state and expiry.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Pilot historical events 533 (Drive) and 719 (Dropbox), with an optional third;
  at least one event has multiple albums. Each shows
  searchable previews and original downloads without moving originals. Record real counts,
  indexing time, storage traffic and failures.
- **SC-002**: On a manager-reviewed pilot sample, report precision, recall and unreadable rate
  separately, including multi-person shots. Do not claim completeness for pending processing.
  Reviewed corrections appear after the next accepted import.
- **SC-003**: With storage calls disabled, metadata search returns the last authorized published
  index. Retries and out-of-order revisions never replace it incorrectly.
- **SC-004**: The identity round trip survives offline save/restart and prevents duplicate-name
  and registered-by confusion; available authoritative bibs require no extra participant input.
- **SC-005**: A first-time manager connects using visible help and its guide. UI/API checks cover
  unsupported formats, missing/invalid index, expired access and read-only restrictions.

## Assumptions

- Existing personal Dropbox capacity is a pilot source, not a promise of unlimited free bandwidth
  or a reason to grant unrestricted access to a personal disk.
- Pilot events supplied by the maintainer: [533](https://universalbicycle.team/ru/calendar/533/)
  and [719](https://universalbicycle.team/ru/calendar/719/). Album links are currently in additional
  materials; inspecting them and historical number files is deferred to the pilot. Event 533 may
  be copied to Dropbox if the maintainer chooses, but relocation is not an architectural requirement.
  Personal matching is not a prerequisite for useful event-level results.
- Face recognition/templates, a photo marketplace and mandatory cloud OCR are outside this first
  design. Face search needs separate identity, consent and deletion requirements.
- This describes proposed behaviour. The maintainer reviews spec and plan before task generation
  and implementation. No application behaviour is changed by this document.
