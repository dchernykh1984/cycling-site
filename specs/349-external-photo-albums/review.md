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
