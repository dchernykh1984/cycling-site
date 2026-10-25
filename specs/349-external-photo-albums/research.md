# Research: indexed albums and issued bibs

**Date**: 2026-10-25. Decisions below are proposals unless attributed to the maintainer.
**Site inspected**: `7b9a65046b576c54cdbe6240aa7055ee20d05271`.
Desktop source observations are from local checkouts on this date; pin their current remote heads
again before a coordinated implementation. No production data or credentials were changed.

## 1. Portable index with a durable derived search index

**Decision**: Originals and previews stay in an album. A versioned manifest is the portable source
for photo observations; the site imports a published revision into PostgreSQL. Manual corrections
are made in the producer and published in a newer revision, so two systems do not author the same
photo observation independently. Manager identity confirmations are separate site facts.

**Rationale**: Reuses existing paid storage, supports local CPU work, avoids remote I/O in search
and permits a different storage service without repeating recognition.

**Alternatives considered**: Download/parse the manifest per search (slow, outage coupling); store
all originals on the site (unnecessary storage cost); require cloud OCR (recurring cost and privacy
change). Later producers may run on a server but must publish the same contract.

The curated gallery currently permits only admin/owner writes and stores originals unchanged:
`specs/site/gallery.md`, `gallery/models.py`, `gallery/actions.py`. Event-manager external albums
need separate write rights without widening administration of the curated gallery.

## 2. Connectors expose capabilities, not a fictional common drive

**Decision**: Required read contract plus optional listing/change/upload capabilities. Bind each
connection to an album root even when the provider token is broader. Initial product adapters are
Dropbox and Google Drive; Dropbox is the first historical pilot. Public HTTPS is a simple portable
reference adapter; Yandex Disk follows separate conformance research.

**Rationale**: Not every source supports write, change cursors or equivalent limited OAuth grants.
An existing read-only album must not require upload permission.

**Alternatives considered**: A provider switch in gallery views (duplicates rules); force all
sources into public URLs (private sharing becomes impossible); demand write access for every album.

Verified primary sources, accessed 2026-10-25:

| Provider | Material finding | Official source |
| --- | --- | --- |
| Drive | `drive.file` is per-file access; `drive.readonly` is restricted, with verification obligations | [Scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth) |
| Drive | Duplicate names can exist in one folder; versions are not a portable content hash; thumbnail links are temporary | [Files resource](https://developers.google.com/workspace/drive/api/reference/rest/v3/files) |
| Drive | Download binary content by ID, checking `canDownload` | [Downloads](https://developers.google.com/workspace/drive/api/guides/manage-downloads) |
| Drive | Changes API exists; some shared links require resource keys | [Changes](https://developers.google.com/workspace/drive/api/guides/manage-changes), [Resource keys](https://developers.google.com/workspace/drive/api/guides/resource-keys) |
| Dropbox | App Folder is confined to the app folder; existing arbitrary folders need another access route | [OAuth](https://docs.dropboxapi.com/dropbox-api/docs/oauth) |
| Dropbox | IDs survive moves; revisions/cursors describe provider state | [File access](https://docs.dropboxapi.com/dropbox-api/docs/file-access) |
| Dropbox | Temporary links expire after four hours and are not recommended for direct browser display | [Temporary links](https://docs.dropboxapi.com/dropbox-api/api-reference/user-endpoints/files/get-temporary-link) |
| Dropbox | Shared-link reading is a separate API capability | [Shared-link files](https://docs.dropboxapi.com/dropbox-api/api-reference/user-endpoints/sharing/get-shared-link-file) |
| Yandex Disk | REST/OAuth and app-folder/read/write scopes exist; detailed ID/change/TTL semantics not yet validated | [Quickstart](https://yandex.com/dev/disk-api/doc/en/concepts/quickstart) |
| HTTPS | Conditional requests can use ETag/Last-Modified where supported | [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html) |

A provider grant and site-enforced root are different controls. Do not promise that selecting a
Drive folder grants every existing/future descendant. Reject ambiguous path resolution rather
than selecting an arbitrary file. Temporary URLs and tokens never enter the portable manifest.

## 3. Return assigned bibs through the exchange that already exists

**Decision (maintainer)**: StartProtocolMaker is the primary source of actually issued bibs.
**Proposed transport**: Keep the registration ID on the start line itself, as an optional trailing
field (variant A in the binding contract); structured bindings beside unchanged lines remain the
alternative (variant B). Preserve existing registration IDs; no global person registry needed.

**Verified path**:

- `api/endpoints/participants.py`: `ParticipantOut.id` and the response's `competition_id` already
  identify the registration and event. This is token-authorized timing data, not a public roster API.
- `StartProtocolMakerPython/app/models.py`: `participant_to_open_line()` turns an API entry into
  `number#name#group#laps#stage#year#team#city#comment#time_shift#` and loses `id`.
- `StartProtocolMakerPython/app/http_io.py`: `upload_start_list()` already POSTs `items`,
  `device_id`, token and monotonic `client_revision` to `/api/v1/start-list/`.
- `api/endpoints/start_list.py`: accepts per-device snapshots, detects old/conflicting revisions,
  and stores opaque lines in `protocols.models.StartListUpload`; it does not bind them to entries.
- `FinishProtocolGeneratorPython/app/models.py`: `competitor_id` is the bib, not a stable account
  or registration reference. `app/http_io.py` currently fetches legacy start-list lines.
- `protocols/document.py`: rows have cells/group/status/note, with unknown fields ignored. Adding
  an unsupported identity field to a generated document alone will not preserve it on the site.

**Rationale**: The fact can return at start registration, before any finish protocol exists. Names,
list ordering and the person who entered a rider are not trustworthy identity keys. In particular,
`registrations/views.py` creates free-mode entries with both `user=user` and `registered_by=user`
while accepting another athlete's entered identity. A non-null registration `user` is therefore not
sufficient evidence for personal photo ownership outside self-only, non-relay registration.

**Readers checked for a trailing field** (2026-10-25): FinishProtocolGeneratorPython reads fields by
index and ignores those past field 9 since its first Python release; WindowsChronometerPython reads
only field 0; the site keeps uploaded lines as opaque strings. The C++ tools are unmaintained and
out of scope by maintainer decision. An older SPM keeps loaded lines but drops the field when it
rebuilds a line from its form; the binding contract says how the site treats that loss.

**Alternatives considered**: The account ID (wrong for several entries per account, free-mode
submitters, relays and on-the-day entrants); the comment field (free text shown in protocols);
a separate assignment endpoint or structured bindings with an offline sidecar (variant B: two
representations of one list that can drift); scraping HTML results (no stable identity); matching
names automatically (ambiguous). See the binding contract for compatibility.

## 4. Historical events are the first useful pilot

**Decision (maintainer)**: Use event [533](https://universalbicycle.team/ru/calendar/533/)
with Drive photos and [719](https://universalbicycle.team/ru/calendar/719/) with collected Dropbox
albums; optionally a third event. Current album links are in additional materials. These source
facts are supplied by the maintainer; inspecting the linked albums is deferred at their request.
**Proposed backfill**: Prefer retained StartProtocolMaker lists; otherwise import start/results
number rows into a reviewed staging set. Normalize names for suggestions only. A manager accepts
or rejects matches against existing registrations and account ownership; ambiguity stays visible.

**Rationale**: The data already exists and can prove usefulness now. Bib search needs only the
correct event and recognized bib, while personal results need an additional identity link.

**Alternatives considered**: Wait for future starts (misses the desired pilot); re-register old
riders (duplicates facts); automatically equate names or registered-by with athlete identity.

Actual album access and retained number files are still to be inventoried during the pilot. Their
availability affects recovered personal links, not support for historical number search. Add a
separate indexed-album section on event pages, retaining general additional materials and the
original links and history. Manager-approved plain photo-link classification can precede indexing;
only a working indexed import enables number search.
Never claim every participant has a known issued bib: the current site computes provisional list
numbers, and historical protocols may have gaps or changes.

## 5. Local CPU producer and visible preparation

**Decision**: Keep the producer runtime separate; choose its engine using labelled pilot photos.
Compare CPU OCR candidates such as PaddleOCR and Tesseract on rotated/occluded bibs and multi-person
shots. Generic text OCR is not proof of reliable bib detection. Report precision/recall and time;
permit corrections and resume. No accuracy or free throughput guarantee is made in this draft.

Primary engine references: [PaddleOCR pipeline](https://paddlepaddle.github.io/PaddleOCR/main/en/version3.x/pipeline_usage/OCR.html)
and [Tesseract documentation](https://tesseract-ocr.github.io/tessdoc/).

**Rationale**: Existing personal storage can avoid a new storage bill; local recognition avoids a
per-image API bill, but CPU time, preview disk, bandwidth and maintenance are still real costs.
**Alternatives considered**: Assume every digit is a bib; install heavy OCR into the Django process;
require photographers to discover a secret index convention themselves.

The setup surface and API expose enabled adapters and schema versions from the actual registry.
Instructions beside the link cover prerequisites, tested tool download/version, exact run steps,
uncertainty review, publication, refresh and recovery. Do not advertise an unshipped indexer or an
unapproved Drive scope as ready. Remaining tool/hosting choices are explicitly gated experiments
for later implementation slices, not hidden requirements imposed on users.

## 6. Existing gallery patterns and external links

Verified `gallery/templates/gallery/albums.html` provides album cards and `gallery/gallery.html`
provides the photo grid/pagination; `gallery/photo.html` provides detail, original download and
previous/next navigation. There is no existing bulk-selection control to claim as reusable.
`calendar_app/templates/calendar_app/detail.html` already separates gallery albums from materials;
`accounts/templates/accounts/profile.html` has registration lists but no personal photo overview.
The new journey contract proposes these additions without changing those templates now.

`calendar_app.models.CompetitionMaterial` currently has title, URL and ordering, with an untranslated
legacy caption and no resource-type field. Photo classification must be an explicit manager fact,
not guessed from a Drive/Dropbox hostname (the same provider can host a video or document). Reuse
the existing material reference/URL; preserve its original label as fallback. New photo-source
display fields follow ru/kk/en rules without inventing translations or rewriting unrelated materials.
