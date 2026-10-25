# Data model: proposed sources, projections and ownership

This is a logical model, not a migration. Reuse existing gallery/event/account rows where their
semantics agree; do not change curated-gallery administration rights to enable external albums.

| Entity | Key facts | Source and relationships |
| --- | --- | --- |
| StorageConnection | Owner, adapter key, secret reference, granted capabilities, health | Provider grant; never expose secrets in album/API responses |
| ExternalAlbum | Site ID, portable album UUID, event, root, localized title/credit, visibility, connection | Manager-owned link; one event per album; many albums per event |
| IndexRevision | Album, producer revision, manifest SHA-256, processing counts, import state | Immutable validated producer snapshot; one published pointer per album |
| IndexedPhoto | Album UUID + photo UUID, original/preview refs and digests, processing state | Derived from published manifest; provider IDs are an internal root-checked cache |
| BibObservation | Photo, exact normalized bib, candidate/accepted/rejected, method/confidence | Manifest source; corrections published there, not independently edited in site DB |
| IssuedBibAssignment | Event, registration reference, bib, source/device/revision, state | SPM authoritative for new races; confirmed historical import for old races |
| AthleteRegistrationLink | Existing registration and confirmed athlete account, provenance | Existing self-registration or reviewed association; registered-by is not athlete identity |
| HistoricalMatchBatch | Event, retained file digest, rows, suggested registration, decision/reviewer | Staging only until manager confirmation; names never act as stable keys |
| ImportJob / ArchiveJob | Owner, bounded inputs, cursor/progress, result/error/expiry | Durable execution state; no unbounded page-request processing |

## Identity invariants

- Namespace registration IDs by site origin and event. Existing numeric IDs suffice; they are not
  credentials. A registration ID cannot be attached to another event by supplying it in a manifest.
- An active issued assignment is unique per event/registration and per event/bib. Reassignment is
  an explicit replacement transaction retaining history, not a silent last-device-wins update.
- Historical rows can remain unresolved without a site registration/account. Keep their source
  and bib for manager review; public photo search does not expose their private imported fields.
- Self-only linked entries are evidence of athlete ownership. Free-mode registered-by and relay
  membership strings are not. No automatic relay-member account linking in the pilot.
- A withdrawn/deleted registration invalidates automatic personal association. Retain only the
  minimum source/audit facts permitted by the existing deletion policy; no duplicated profile.

## Photo/index invariants

- Portable identity is `(album_uuid, photo_uuid)`; moving a verified album does not mint new IDs.
  A second site connection cannot claim the same UUID without ownership and source-move validation.
- Provider path or ID changes do not change photo identity. Changed content requires a newer
  manifest entry and checksum; stale originals never silently replace a verified asset.
- Provider revision tokens are opaque and scoped to that adapter. Manifest revisions order one
  album's publication; SHA-256 verifies bytes. None is a substitute for the others.
- Processing states distinguish pending, processed and failed. An empty bib list after processing
  means no accepted bib was found, not proof that no rider is present.
- Only accepted observations enter normal matches; uncertain candidates are a separate manager
  review surface. Exact normalization retains leading zeroes and never maps unrelated digit text.

## State transitions

**Connection**: pending -> ready; ready -> reconnect-required / forbidden / throttled / unavailable;
recovery -> ready; disconnect -> disabled. Disconnection immediately disables site media delivery;
manager can separately unpublish indexed metadata or retain it if publication rights remain valid.

**Index import**: queued -> reading -> validating -> staging -> published, or failed/cancelled.
Validate complete input and stage under a new revision; publish pointer and derived rows atomically.
The old pointer remains until publication. A partial producer snapshot can publish usable partial
results but cannot remove existing photos; only explicit removals in a newer revision can do so.

**Binding**: unresolved -> confirmed; confirmed -> superseded/revoked/conflicted. Conflicting new
proposals leave historical confirmed facts intact but suppress disputed personal matching until
resolved. Explicit manager resolution records the competing sources and chosen replacement.

**Historical import**: staged -> suggested -> reviewed -> committed; rejected/unresolved rows stay
separate. Re-importing the same file and choices is idempotent. Corrections are new reviewed
revisions and cannot overwrite a current authoritative SPM assignment silently.

**Archive**: queued -> preparing -> ready / partial / failed / cancelled -> expired. Ready/partial
results are owner-bound; access checks at execution and retrieval can remove newly hidden files.

## Access and retention

Event managers edit only their event's external albums and historical matches. Admin/owner rights
are explicit; existing curated albums keep current rules. Readers see only allowed event/album
metadata. Personal queries use the requesting athlete's confirmed links; arbitrary account-ID
queries are not offered to ordinary readers.

Credentials are server-held secret references; portable indexes have no names, dates of birth,
account IDs, email or face templates. A public manifest still reveals event bib observations:
explain this before choosing public sharing. Generated previews remove unnecessary embedded
metadata; originals remain unchanged and may retain camera/location metadata.

Import limits, worker concurrency, archive byte/photo limits and TTL are named settings with
visible values. Pilot defaults are selected from actual counts/hosting capacity before rollout.
Disconnect never deletes provider originals. Site photo removal and job cleanup occur after the
transaction commits; archived files are deleted on expiry, cancellation or access revocation.
