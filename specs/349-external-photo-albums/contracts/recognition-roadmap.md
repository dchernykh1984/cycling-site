# Retained recognition scenarios and decision gates

This contract preserves the broader discussion. The first independent pilot uses bib numbers and
local CPU indexing. Deferred scenarios remain feature requirements for later reviewed slices;
their presence here is not approval to implement every producer or process face data now.

## D1 - Local automatic bib and appearance recognition (approved slice)

**Decision (maintainer, 2026-10-25)**: no face recognition and no selfie search. Riders are
matched by their overall look -- kit, bike, build, helmet -- because at amateur races few riders
share all of those. Faces are not detected, compared or stored for this.

### Automatic indexing (maintainer, 2026-10-26)

One `Recognize automatically` button runs sequential phases. A dropdown offers `Bib numbers only`
and `Bib numbers, then rider appearance`, with the second selected by default. The desktop app
uses pinned PP-OCRv3 text detection and PP-OCRv5 English reading, NanoDet person detection
and Youtu whole-body ReID
through ONNX Runtime on CPU. No face detector, face embedding or selfie is used. The person crop
contains kit, helmet and build, and bike pixels falling within that crop. A bike detector or a
cyclist-specific model can be evaluated later; it is not a claim of this implementation.

First use downloads up to 11 MB for OCR or 121 MB for both phases, with visible progress and
verified hashes; subsequent runs work offline. Photos never go to a recognition service. The
initial implementation searches one album of one event at a time. Cross-album appearance search
is not yet implemented: no implicit association across arbitrary open folders or events.

OCR confidence >= 0.95 is accepted, >= 0.60 is a candidate; values retain case and leading zeroes.
Large photos are read as overlapping 768-pixel tiles; rider detection preserves image aspect
with padding and maps boxes back to the oriented original. The current reader supports digits and Latin bibs; other scripts remain available through manual
entry/CSV. ReID cosine similarity >= 0.80 suggests a candidate. These are provisional model
thresholds, not measured race accuracy. Appearance never becomes accepted automatically.

Every photo is saved as an atomic revision. Stop keeps OCR checkpoints; resuming skips unchanged
OCR for the same model version and recomputes appearance. Vectors live only in a private temporary
database outside the album and are deleted on exit. Concurrent index edits stop the worker.
Manual acceptance, rejection and an empty accepted-set lock survive automatic runs; changed
original bytes archive the old manual review and invalidate all old automatic observations.

### Matching rules

1. Detect person crops in every photo of the open album; do not mix events.
2. Seeds: a rider crop that contains an accepted bib's `region`. A bib region inside two crops
   (riders overlapping) seeds nothing on that photo.
3. Describe every crop with the pinned Youtu whole-body appearance model.
4. For each bib, look in the open album for crops close to any of its seeds. Recall
   comes first: the maintainer accepts that up to about half of the suggestions are wrong, while
   a missed photo of the rider is the worse failure. The threshold is set from the pilot sample.
5. A relay bib's seeds can show several people. Retain every seed appearance and search their union; everything found goes to the team's registration album.
6. A match is published as an observation with `method: appearance`, always `candidate`, with its
   score and region. It never becomes an accepted bib by itself; the participant's "this is me" /
   "not me" decides (see the [data model](../data-model.md)).

Within one event only: kit and bike change between events. Appearance vectors stay with the
producer; the album index carries only the candidate bib, score and region, so nothing in the
public folder describes a person beyond the photo itself.

Acceptance for that slice: on a labelled pilot sample, a rider whose bib is readable on some
photos is suggested on photos of the same event where it is not; report the share of the rider's
real photos found and the share of wrong suggestions; a relay bib yields one cluster per member;
an overlapping seed is not used. Measure CPU time per photo.

**Pilot acceptance still open**: measure precision, recall and CPU time on events 533/719; compare
models and tune thresholds from labelled photos. An actual 158-photo race album was exercised locally; without a complete manually labelled
reference, result counts do not prove precision or recall. Synthetic and mocked regressions
cover the scale and geometry failures found by that pilot. Source models/licenses/hashes are recorded in SportPhotoIndexer
`MODEL_NOTICES.md` and `app/model_catalog.json`.

## D2 - Slow background indexing on site resources (optional producer)

A manager connects an album and, where explicitly enabled with necessary source/publication
access, requests site-side indexing. A bounded worker gradually processes photos using spare
capacity instead of asking for a locally generated index. Available partial snapshots become
searchable while the rest are pending.

Specify configurable schedules, concurrency, CPU/time/memory budgets, pause/resume/cancel,
per-photo checkpoints, progress/retries and manifest revision ownership. "While idle" means an
operationally configured background budget, not an assumption that the host offers unlimited free
CPU or that a page request can run recognition. Heavy work must not starve normal site requests.
The same producer publishes assets then a valid portable manifest; the same importer consumes it.
A read-only connection does not acquire write rights implicitly, nor can it publish into that root.

Acceptance: stop/restart midway, resume without reprocessing completed unchanged photos, retain
manual decisions, keep the site responsive, and make only valid partial revisions visible.
Show actual processed/total/inventory-complete states, not a blank gallery until everything finishes.

**Open decision**: hosting capacity, scheduling/worker deployment and publication access. Reuse the
local/third-party index path when this producer is unavailable. No server OCR is implemented here.

## D3 - Independent and cloud producers (optional alternatives)

A photographer, organizer or unrelated program can create the published format. Connecting a
valid ready index must not require running the site's preferred OCR engine or repeating OCR.
Any future Google/Amazon/specialized recognition integration is another index producer; its
provider choice is configuration, independent of storage adapters and gallery queries.

Paid processing is opt-in with visible limits/estimate or budget before starting; do not trigger
an unannounced bill simply because an organizer uploaded a photo. A particular engine, cloud
service or a new paid subscription is not required to use the local-index pilot. Record local
CPU time, temporary space and storage/delivery traffic separately from any recognition API charge;
already-paid storage does not imply unlimited free traffic or hosting resources.

Acceptance: import a third-party-produced compatible index without re-recognition and obtain the
same matches; an unavailable paid service does not block reading the last valid published index.
Unsupported schema versions name the supported versions and preparation guide.

**Open decision**: whether any cloud producer is needed after measuring local/server options.
No vendor or paid plan is selected by this design.

## Shared producer behaviour - Roster hints and corrections

Where authorized issued-bib data exists, export/reuse it as optional recognition hints rather than
asking people to type the roster again. Use confirmed numbers from the SPM/site binding path;
provisional list positions or names alone cannot supply authoritative bibs. Avoid unnecessary
private profile fields in a producer hint file and never include those facts in the public index.

Hints can improve candidate review but are not a complete allowlist: historical lists can be
incomplete and on-the-day entrants may be absent. A detected number outside the known roster
remains reviewable/searchable under the same acceptance policy, not silently discarded.
All producers preserve the [manual precedence rules](photo-index.md), stable IDs, unchanged
originals, resumable checkpoints and atomic publication. Engine changes cannot erase reviewed data.
