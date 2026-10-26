# Document review log

**Scope**: Constitution amendment and issue #349 design, not implementation validation.
The shipping workflow calls for three self-review cycles; accepted findings get separate commits.

Reviews will check user requirements and existing behaviour, then cross-contract consistency,
then failure paths and readiness. This log records outcomes after those checks, not advance approval.

## Cycle 1 - Source and requirement validation

**Accepted finding R1**: A non-null registration `user` can be the submitter in free mode,
not the named athlete. Verified `registrations/views.py` sets both `user` and `registered_by`
while accepting free-form identity. Restricted automatic ownership to self-only, non-relay
entries and documented separate confirmation elsewhere, including the regression scenario.

**Result**: The design no longer treats this existing field as universal proof of athlete identity.
No application change is included.

## Cycle 2 - Cross-contract consistency

**Accepted finding R2**: `processed == total` could make an interrupted initial scan look like a
complete album, because the importer cannot see undiscovered files. Added machine-readable
`inventory_complete`, required it for `complete`, updated the sample/model and acceptance runbook.
A local diagnostic alone would not satisfy the transparent-setup principle.

**Result**: Readers can distinguish a complete inventory from only the discovered subset.

**Accepted finding R3**: The scope paragraph put event 533 before enabling its Drive connector,
while delivery slice 4 added that connector. Aligned the scope and acceptance order: Dropbox pilot
719 first, Drive pilot 533 once the Drive slice exists. No mandatory album relocation was added.

## Cycle 3 - Failure paths and readiness

**Accepted finding R4**: A source-of-truth manifest plus repeated resync could resurrect a photo
removed on the site. Separated site-owned publication decisions from producer-owned recognition
facts, made suppression persistent across imports and required explicit restoration. Added API
coverage and an archive/resync acceptance scenario; originals remain external and unchanged.

**Result**: Three document review cycles completed, with R1-R4 addressed in separate commits.
Document checks do not establish provider access, OCR accuracy or deployed feature readiness.
Spec/plan still require maintainer review; no application code or production albums changed.

## Follow-up scope - Event and cabinet journeys

The maintainer requested explicit personal-photo versus all-album navigation after the initial
three cycles. Added a dedicated journey contract and synchronized spec, plan, model, API and
acceptance runbook. Reviewed the addition in three passes: existing gallery/event/profile seams;
personal-versus-source grouping and guest/identity scope; pagination, account-switching and removal
failure paths. Verified bulk selection is a new control, not existing gallery behaviour, and
separated plain-link classification from successful index import. No unresolved findings remain
in these document passes. These are proposed screens,
not implemented UI or evidence of a working personal gallery.

## Completeness audit - Organizer input paths

**Accepted omission R5**: Conversation and issue scenario 4 require uploading through the site
into selected external storage. Earlier contracts mentioned only an optional adapter upload
capability, not a shippable user flow. Added story 6, FR-020, upload contract, UI/API operations,
job states and retry/indexing acceptance. A capability flag does not satisfy the user scenario.

## Completeness audit - Reviewed recognition outcomes

**Accepted omission R6**: The index could record corrections but did not explicitly prevent OCR
from overwriting them on reindex. Added FR-021 and normative acceptance/rejection precedence,
content-digest binding, optional reviewed-set locking (including no accepted bibs), sample fields
and repeat/model-change/source-move acceptance scenarios. Changed-image review retains audit.

## Completeness audit - Retained broader recognition scope

**Accepted omission R7**: Face/selfie search and slow server recognition were named as deferred,
but did not retain the user's scenarios and acceptance. Added D1-D3 with explicit model/private
format/access/retention and resource/publication gates, independent third-party/cloud producers,
optional issued-roster hints and cost boundaries (FR-022/023). These are later reviewed slices,
not implemented features or a decision to require paid recognition.

## Coverage verification passes

1. Compare issue scenarios, comments and later maintainer decisions against spec stories/FRs.
2. Check each added requirement reaches plan, applicable contracts and acceptance scenarios.
3. Probe regression edges: read-only upload, uploaded-not-indexed status, rerun/manual rejection,
   changed bytes, unknown-roster bibs and deferred capability labels versus actual first-pilot scope.

The [coverage matrix](requirements-coverage.md) records C01-C30, separates later-stage wishes from
first-pilot requirements and keeps unresolved implementation choices visible. Documented coverage
is not implementation proof; only specification artifacts changed in this audit.

## Maintainer review of 2026-10-25 and cycle 4

The maintainer's additions (C31-C37) changed the start-line binding to a recommended trailing field
(variant A, with the structured envelope kept as variant B), added athlete ownership for several
entries and relay slots, the bib-seeded face route, previews as an album requirement, site-hosted
storage as an adapter and a manual indexing mode. A self-review of those changes found:

**Accepted finding R8**: "Non-numeric markers assign no bib" contradicted the index rule that bibs
keep letters and leading zeroes. Only an empty field 0 and SPM's `NOT_PAID` now assign nothing.

**Accepted finding R9**: A line whose stage field is N > 1 owns N consecutive bibs, as FPG reads it.
The binding contract treated a line as one bib. All stage bibs now go to the line's registrations
as team bibs; the member of each stage is not inferred.

**Accepted finding R10**: The plan's VII/XI gate still described only the acknowledged structured
fields. It now states the compatibility evidence for both variants.

## Maintainer decisions of 2026-10-25 (second round) and cycle 5

Decisions recorded: variant A adopted, with the reference as a visible form field kept on both
lists; one album per registration (C33) and a coach's view once #315 exists (C40); appearance
instead of faces (C26, C31); participant "this is me" / "not me" marks kept apart from the
folder index, refreshed only on request (C41, C42); Dropbox alone first, tiny thumbnails on the
site and the photo opened in Dropbox (C43). A self-review of those changes found:

**Accepted finding R11**: The index contract still rejected any processed photo without an album
preview, while the connector let Dropbox thumbnails stand in. Import now rejects a photo only when
it has neither; whether album previews stay mandatory is an open question.

**Accepted finding R12**: The journeys still sent a thumbnail click to a site photo page with an
original download. A click now opens the photo in Dropbox in a new tab.

**Accepted finding R13**: FR-012 still promised individual downloads from the site. A single photo
is now viewed and downloaded in the storage; archives come after the first slice.

## Maintainer decisions of 2026-10-25 (third round)

Recorded: who marks photos and how a cross is final (C44); reading with the site's own Dropbox app
and per-file links from the indexer, thumbnails straight from Dropbox where the index allows (C45);
event 533 set aside until re-uploaded to Dropbox; existing indexing tools surveyed (C46). The
Dropbox authentication types were checked against the API reference, not tried; the concept check
with a 58 KB test album is prepared for when the site's Dropbox app exists.

## External review of the implementation plan (2026-10-26)

A second agent reviewed `tmp/plan.txt` (15 findings, all accepted). Those that change contracts
are recorded here; the rest changed only the plan.

- Start line: absent and empty field 10 are now distinct (11 separators mean the field is
  present), so a referee's unlink is not mistaken for an older SPM's loss; stage expansion is
  bounded before it runs.
- Decisions: an undo reverts one recorded transition, only while it is the latest and in its
  window; team-mates sharing a bib keep their own marks, and event search drops a photo only when
  every holder of the bib said "not me". Bib assignments get their own append-only history, since
  the generic audit log keeps only changed field names.
- Thumbnails: stored where `serve_media` (which serves `MEDIA_ROOT` unchecked) cannot reach them, served by a
  permission-checked view with private caching, named by internal IDs plus source digest and
  regenerated when it changes; originals over 20 MB without a preview are flagged to the organizer.
- Portable album UUIDs are unique on the site; `sha256` is never a provider's own hash.
