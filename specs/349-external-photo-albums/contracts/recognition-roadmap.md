# Retained recognition scenarios and decision gates

This contract preserves the broader discussion. The first independent pilot uses bib numbers and
local CPU indexing. Deferred scenarios remain feature requirements for later reviewed slices;
their presence here is not approval to implement every producer or process face data now.

## D1 - Search by a face/selfie (later slice)

A participant can search an allowed event using their own reference photo when the bib is not
visible or was not recognized. Results are thumbnails with the same individual/selected/all
allowed downloads. Event selection and album visibility still apply; do not implement a global
search for arbitrary people across private events. Number search remains independently useful.

An authorized reusable reference, if the participant chooses to save one, avoids asking for the
same selfie at every event. Its purpose, reuse and removal are explicit; a profile avatar is not
automatically a face-search authorization. "Photos with me" must explain whether it uses issued
numbers or an explicitly enabled face capability, rather than silently changing its meaning.

Before implementation, specify the matching engine/model version, compatible private index format,
reference and template storage/retention/deletion, who can initiate a query, event eligibility,
quality/uncertainty thresholds and any needed permission/consent workflow. Portable public bib
manifests never acquire face vectors or identity records. A versioned private face extension must
not require redoing ordinary bib indexes or tie the gallery to a particular storage provider.

Acceptance for that slice: a visible face with no readable bib can be found through the face
capability; mismatched model/index versions are actionable errors; unsupported events do not ask
for a selfie; reference reuse and removal have visible effects. API permissions equal the UI.
False matches, processing times and face quality are measured on authorized pilot samples.

**Open decision**: engine and private face contract, supported query authority, retention and
release timing. Do not claim this is included in the number-only pilot or silently drop the wish.

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
