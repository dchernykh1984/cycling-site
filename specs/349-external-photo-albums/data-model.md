# Data model: proposed sources, projections and ownership

This is a logical model, not a migration. Reuse existing gallery/event/account rows where their
semantics agree; do not change curated-gallery administration rights to enable external albums.

| Entity | Key facts | Source and relationships |
| --- | --- | --- |
| StorageConnection | Owner, adapter key, secret reference, granted capabilities, health | Provider grant; never expose secrets in album/API responses. Reading a Dropbox shared link needs none: the site's own app credentials are a setting, not a connection |
| ExternalAlbum | Site ID, portable album UUID, event, root, localized title/credit, visibility, connection | Manager-owned link; one event per album; many albums per event |
| IndexRevision | Album, producer revision, manifest SHA-256, processing counts, import state | Immutable validated producer snapshot; one published pointer per album |
| IndexedPhoto | Album UUID + photo UUID, original/preview refs and digests, processing state, site copy of the preview | Derived from published manifest; provider IDs are an internal root-checked cache; the preview copy is replaced when its digest changes |
| BibObservation | Photo, exact normalized bib, candidate/accepted/rejected, method/confidence | Manifest source; corrections published there, not independently edited in site DB |
| IssuedBibAssignment | Event, registration reference, bib, source/device/revision, state | SPM authoritative for new races; confirmed historical import for old races |
| AthleteRegistrationLink | Registration, optional member slot, confirmed athlete account, provenance | Self-only entry, "this is me" at submission, accepted claim or manager decision; registered-by is not athlete identity |
| HistoricalMatchBatch | Event, retained file digest, rows, suggested registration, decision/reviewer | Staging only until manager confirmation; names never act as stable keys |
| ClassifiedPhotoLink | Existing material reference, manager classification, localized display override/fallback | Ordinary external source, no index required; URL stays on original material |
| PublicationDecision | Album/photo visibility or removal, actor, reason, restoration history | Site-owned publication overlay; not a competing source for recognized bibs |
| ParticipantPhotoDecision | Registration, `(album_uuid, photo_uuid)`, "this is me" / "not me", actor (athlete or coach), time | Site-owned, one per album and photo; check -> cross allowed, cross is final (bar an immediate undo); survives index refreshes; kept when a photo leaves the index and applied again if it returns |
| UploadJob / UploadItem | Event/root, owner, per-file digest/reference/session, transferred bytes and accepted state | Provider-backed resumable transfer; no duplicate durable original on site |
| ImportJob / ArchiveJob | Owner, bounded inputs, cursor/progress, result/error/expiry | Durable execution state; no unbounded page-request processing |

## Identity invariants

- Namespace registration IDs by site origin and event. Existing numeric IDs suffice; they are not
  credentials. A registration ID cannot be attached to another event by supplying it in a manifest.
- An active issued assignment is unique per event/registration and per event/bib. Reassignment is
  an explicit replacement transaction retaining history, not a silent last-device-wins update.
- Historical rows can remain unresolved without a site registration/account. Keep their source
  and bib for manager review; public photo search does not expose their private imported fields.
- Self-only, non-relay entries linked to the account are evidence of athlete ownership. In the
  current free-mode submission path, both `user` and `registered_by` can identify the submitter
  rather than the named athlete (`registrations/views.py`). Neither field alone proves ownership
  there. Require a separately confirmed athlete link; relay strings are not account links either.
- Ways to confirm the athlete of a free-mode entry: an explicit "this is me" choice at submission
  (prefilled, never assumed, when the entered name and birth date equal the account's profile);
  a claim link the submitter passes to the athlete, accepted by the athlete signed in to their own
  account; or a manager decision. A claim changes who the athlete is, not who may edit the entry.
- A relay registered as one entry has member slots: (registration, position in
  `participant_names`). Each slot can get its own confirmed athlete by the same claim route; a
  member name string never links an account by itself. A team that SPM assembles from separate
  registrations links each member through that member's own registration.
- Personal albums are per registration. An account that filed several registrations at one
  event (two distances, itself and its children) has one album per registration, titled with the
  entrant's name and bib; nothing forces one entry per account per event.
- A relay bib (or a multi-stage line's set of stage bibs) matches the team, not a member: each
  confirmed member sees the team's bib photos labelled as team photos, because the bib does not
  say which member is in the frame. Only a later face slice can narrow that (see the
  [recognition roadmap](contracts/recognition-roadmap.md)).
- Who sees a registration album: the account that filed it, its confirmed athlete, members who
  claimed a relay slot and, once the coach role of #315 exists, the athlete's coach. A trainee sees
  only their own albums. A submitter's album for someone else reveals nothing beyond event-level
  search for a number the submitter already knows.
- A withdrawn/deleted registration invalidates automatic personal association. Retain only the
  minimum source/audit facts permitted by the existing deletion policy; no duplicated profile.

## Photo/index invariants

- Portable identity is `(album_uuid, photo_uuid)`; moving a verified album does not mint new IDs.
  A second site connection cannot claim the same UUID without ownership and source-move validation.
- Provider path or ID changes do not change photo identity. Changed content requires a newer
  manifest entry and checksum; stale originals never silently replace a verified asset.
- Provider revision tokens are opaque and scoped to that adapter. Manifest revisions order one
  album's publication; SHA-256 verifies bytes. None is a substitute for the others.
- Inventory completeness is explicit and independent of per-photo progress; a stopped scan with
  all discovered photos processed must not look like a complete album.
- Processing states distinguish pending, processed and failed. An empty bib list after processing
  means no accepted bib was found, not proof that no rider is present.
- Manual observations bind to the reviewed original digest and override automatic outcomes.
  Reindexing preserves manual rejections as well as acceptances; an optional reviewed-set lock
  can preserve an empty accepted set. Changed bytes invalidate application, not the audit trail.
- Only accepted observations enter normal matches; uncertain candidates are a separate manager
  review surface. Exact normalization retains leading zeroes and never maps unrelated digit text.

## State transitions

**Connection**: pending -> ready; ready -> reconnect-required / forbidden / throttled / unavailable;
recovery -> ready; disconnect -> disabled. Disconnection immediately disables site media delivery;
manager can separately unpublish indexed metadata or retain it if publication rights remain valid.

**Index import**: started when an organizer adds an album or presses "Refresh participants'
tagging", never by polling. queued -> reading -> validating -> staging -> published, or failed/cancelled.
Validate complete input and stage under a new revision; publish pointer and derived rows atomically.
The old pointer remains until publication. A partial producer snapshot can publish usable partial
results but cannot remove existing photos; only explicit removals in a newer revision can do so.

**Binding**: unresolved -> confirmed; confirmed -> superseded/revoked/conflicted. Conflicting new
proposals leave historical confirmed facts intact but suppress disputed personal matching until
resolved. Explicit manager resolution records the competing sources and chosen replacement.

**Historical import**: staged -> suggested -> reviewed -> committed; rejected/unresolved rows stay
separate. Re-importing the same file and choices is idempotent. Corrections are new reviewed
revisions and cannot overwrite a current authoritative SPM assignment silently.

**Upload**: queued -> transferring -> uploaded / partial / failed / cancelled. Uploaded is not
indexed; preserve per-file acceptance through retry. Staging/session cleanup cannot delete
unrelated or previously published external files. Recognition/import track their own states.

**Archive**: queued -> preparing -> ready / partial / failed / cancelled -> expired. Ready/partial
results are owner-bound; access checks at execution and retrieval can remove newly hidden files.

## Event album source projection

The all-albums view unifies visible curated albums, indexed external albums and explicitly
classified photo material links. Reference existing rows/URLs; do not create a second stored copy
of a material URL. Classification is independent of indexing and never infers resource type from
a provider hostname. A classified plain link has no fabricated photo count or number search.

## Personal gallery projections

A registration album is a query projection, not another stored album: the registration's
confirmed bib(s) joined to the event's visible accepted matches and candidates, then that
registration's own decisions applied -- "this is me" marks a photo confirmed, "not me" hides it
from that album and from the event's search for that registration's bib, not from anyone else's. Unchecked candidates stay visible and marked, because a missed photo is
worse than a wrong suggestion (maintainer, 2026-10-25). Count distinct `(album_id, photo_id)` results and select covers
only from that set; several source albums at the event stay one registration album, with a
source filter. Registrations with pending number/index data keep an explicit state instead of
disappearing from the overview.

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
A site-owned publication overlay is applied after every import: hidden/removed albums and photos
stay suppressed across newer producer revisions, source moves and retries. Only an explicit
authorized restore changes it. Keep the minimal stable identity needed to enforce suppression;
this is a visibility fact, not a second source of recognition observations. Recheck it for cached
media and all archive states. A new producer index cannot undo a site removal.

Disconnect never deletes provider originals. Site photo removal and job cleanup occur after the
transaction commits; archived files are deleted on expiry, cancellation or access revocation.
