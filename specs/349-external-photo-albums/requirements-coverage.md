# Requirements coverage: issue #349 and the photo-feature discussion

**Audited**: 2026-10-25, against the issue body/comments and the conversation through the request
to check completeness. This matrix records documented coverage, not implemented functionality,
provider/OCR validation or approval of every open design choice. Only photo-feature requests belong
here; earlier unrelated pull-request and map-service work is outside this feature.

Sources: [issue #349](https://github.com/dchernykh1984/cycling-site/issues/349), its
[organizer-upload comment](https://github.com/dchernykh1984/cycling-site/issues/349#issuecomment-6363449756),
[portable-index comment](https://github.com/dchernykh1984/cycling-site/issues/349#issuecomment-6387779979),
and the maintainer's later conversation decisions (SPM authority, transparent setup, historical
pilots, event/cabinet navigation and specification-only scope).

## Organizer input and producer independence

| ID | Discussed requirement | Normative coverage / acceptance |
| --- | --- | --- |
| C01 | Organizers manage their own event albums; existing curated showcase survives | FR-007/013; [model](data-model.md), [API permissions](contracts/api-and-setup.md) |
| C02 | Upload photos through the site into configured external storage | Story 6, FR-020; [upload/resume contract](contracts/uploads.md) |
| C03 | Alternatively connect an already prepared album with index | Story 1, FR-002/003/023; no recognition repeated for a compatible third-party index |
| C04 | A local computer can index on CPU and write the file next to photos | Story 2, FR-005/006; [research](research.md), [local guide requirements](contracts/api-and-setup.md) |
| C05 | Originals stay unchanged; generate separate previews | FR-002/020; [portable index](contracts/photo-index.md), original integrity acceptance in quickstart |

## Storage and indexing

| ID | Discussed requirement | Normative coverage / acceptance |
| --- | --- | --- |
| C06 | Storage can be anywhere via connectors, not hardcoded personal Dropbox | FR-001/023; [connector contract](contracts/connector.md), Drive/Dropbox initial, HTTPS reference, Yandex extension |
| C07 | Open versioned manifest usable by independent tools; keep links on storage moves | Story 5, FR-002/023; stable album/photo IDs, relative refs, revision and SHA-256 in index contract |
| C08 | Several or no bibs per photo, confidence, versions and explicit processing states | FR-002/004; index contract; no-detection differs from pending/failed, inventory completeness explicit |
| C09 | Site caches/imports index rather than scanning provider on every search | FR-003/004; durable DB projection, atomic publish, zero-provider-call metadata search acceptance |
| C10 | Manual corrections survive automated reruns; partial work resumes | FR-004/021; accepted/rejected precedence, optional review lock, model-change and resume scenarios |

## Participant search and download

| ID | Discussed requirement | Normative coverage / acceptance |
| --- | --- | --- |
| C11 | Search one event by an explicitly entered bib | Story 1, FR-008; works without account-to-bib mapping; multiple albums per event |
| C12 | My photos at one event without re-entering a known issued number | Story 3, FR-008/009/015; confirmed athlete link and existing SPM return path |
| C13 | All my photos across events with grouping and thumbnails | Story 3, FR-008/019; [personal event-card/grid journeys](contracts/user-journeys.md) |
| C14 | Download one, selected, all at an event or all personal photos across events | Story 4, FR-012; same journey contract, bounded archive jobs, pagination/selection and partial-file reports |
| C15 | Background processing yields more results progressively, with truthful states | Story 1, FR-004/006; processing/inventory counts; D2 retains optional site-side producer |

## Identity and historical races

| ID | Discussed requirement | Normative coverage / acceptance |
| --- | --- | --- |
| C16 | Do not assume registration list numbers are the physically issued numbers | FR-009/011; research identifies the existing provisional numbering and lost registration reference |
| C17 | SPM is the primary assigned-number source; preserve registration references across tools | Maintainer decision; FR-009/011; [acknowledged start-list binding contract](contracts/start-list-bindings.md), offline persistence and FPG compatibility |
| C18 | Recover old mappings from names/results only with review; consider a cross-tool ID | FR-010; staged candidate matches, ambiguity and provenance; names/transliteration are suggestions, existing origin/event/registration ID suffices for proposed round trip |
| C19 | Entry for someone else is not my participation; handle relays, equal names and reused bibs | FR-008/010/015; model invariants; free-mode `user`/`registered_by` insufficient, event-scoped bindings, no inferred relay-member accounts |
| C20 | Pilot old races now, rather than wait for a new event or re-register riders | Story 1, SC-001; events 533 (Drive) and 719 (Dropbox), optional third; inspect their real albums/number files later as requested |

## Navigation, preparation and operational constraints

| ID | Discussed requirement | Normative coverage / acceptance |
| --- | --- | --- |
| C21 | Distinguish Photos with me from ordinary album links | FR-017/019; one event photo entry, personal cards and labelled sources within its overview (2026-10-27 revision) |
| C22 | Cabinet uses gallery-style albums and the same per-event personal thumbnail view | FR-019; one virtual card per event, own-photo covers/counts, source album/photographer filter inside |
| C23 | Keep additional materials for video/clips/documents; move photo sources without data loss | FR-017/018; explicit classification, existing URL reference, no double rendering or silent deletion |
| C24 | Ask known facts only once; explain support, format and preparation beside the link | Constitution XIII/XIV; FR-006/015; supported services/versions/sample, tested local-tool guide, access/costs and actionable retained-value errors |
| C25 | Same functions through API; localized and accessible views; private data and bounded work | FR-012/013/014/016/018; shared permissions, 404, credential/root isolation, archive limits, removal persists across resync |

## Retained later-stage wishes

| ID | Discussed requirement | Coverage and deliberately open decisions |
| --- | --- | --- |
| C26 | Find photos when a bib cannot be read | D1 in the [recognition roadmap](contracts/recognition-roadmap.md): by overall appearance seeded from the rider's bib photos; face and selfie search dropped by the maintainer (2026-10-25) |
| C27 | Site can slowly recognize photos using spare CPU instead of requiring local indexing | D2, same roadmap: scheduled resource budgets, checkpoints/pause/resume, partial results and required publication access; hosting/worker choice remains open |
| C28 | Third-party, Google/Amazon or another paid recognizer can generate the same index | D3 and FR-023: optional producer choice independent of storage; opt-in budget, no mandatory paid service or unannounced processing bill |
| C29 | Known issued bibs can aid recognition; unknown old/on-the-day entrants still work | FR-022; roadmap shared producer rules; reuse authorized hints, not a complete allowlist |
| C30 | Reuse already-paid 2 TB storage; distinguish recognition from storage/serving costs | FR-006/023; research and roadmap separate local CPU, paid OCR, capacity, traffic and temporary resources; no unconditional free-service promise |

## Additions from the maintainer's 2026-10-25 review

| ID | Discussed requirement | Normative coverage / acceptance |
| --- | --- | --- |
| C31 | Find the same rider where the bib is hidden, from their bib photos | D1 in the [recognition roadmap](contracts/recognition-roadmap.md): overall appearance, not faces (maintainer decision); optional bib `region`; `method: appearance` candidates |
| C32 | A relay shares one bib among several very different people | FR-024; relay member slots and team-photo label in the [data model](data-model.md); one appearance cluster per member in D1 |
| C33 | One account may file several entries for one race | FR-024: one album per registration, titled with the entrant's name and bib |
| C40 | A coach (issue #315) sees all trainees' albums; a trainee only their own | FR-025, conditional on the role being added |
| C41 | Participants mark photos "this is me" / "not me"; candidates shown recall-first | FR-026; [index contract](contracts/photo-index.md), registration grid in the [journeys](contracts/user-journeys.md) |
| C42 | Validate a local index by keeping participant decisions apart; refresh on adding an album or on request | FR-026; ParticipantPhotoDecision in the [data model](data-model.md) |
| C43 | Tiny thumbnails on the site, the photo opened in Dropbox on click; Dropbox-only connector first | FR-001/003; delivery in the [connector contract](contracts/connector.md); research section 7 |
| C44 | Only the athlete or their coach marks; a check can become a cross, a cross is final | FR-026; decisions in the [index contract](contracts/photo-index.md) and [journeys](contracts/user-journeys.md) |
| C45 | No broad token from organizers; ideally no thumbnails stored on the site | FR-003; [connector](contracts/connector.md): app authentication for reading, per-file `view_url` made by the indexer, site thumbnails only as fallback |
| C46 | Are there existing projects that index automatically? | [Research section 8](research.md): Immich, bibnumber, commercial services; none produces the index as is |
| C47 | A coach or athlete representative (#315) registers trainees in batches and manages their photos | FR-025; who marks in the [index contract](contracts/photo-index.md) |
| C48 | External albums are added by the event's creator or an admin, with their token if one is ever needed; indexing instruction beside the form | FR-006/007; [data model](data-model.md) |
| C49 | Organizer statistics of confirmations and rejections | FR-027; [API matrix](contracts/api-and-setup.md) |
| C34 | Keep the bib-to-entry link through SPM without losing plain text files or existing readers | FR-009/011; [binding contract](contracts/start-list-bindings.md) variant A (trailing field) adopted by the maintainer, readers checked |
| C35 | Thumbnails are a requirement on the album and live in it | FR-002; preview rules in the [index contract](contracts/photo-index.md) |
| C36 | Moving storage onto the site later only swaps the connector | FR-001; site-hosted storage in the [connector contract](contracts/connector.md) |
| C37 | The uploader indexes, by OCR or by hand with our tool | FR-005 manual mode; same format, `method: manual` |
| C38 | Check that storage services allow reading albums and showing photos without copying them to the site | [Research section 7](research.md): reading works on Dropbox and Drive, direct display does not; FR-003 copies previews, originals by provider URL or budgeted proxy; Google Photos excluded (FR-001) |
| C39 | Check that the proposed logic holds | Research section 7: bib index sound with manual review; faces weak under helmets and sunglasses, which is why D1 uses overall appearance |

## Actual gaps versus unresolved choices

The audit found and added the previously incomplete website-upload scenario (R5), manual-priority
rule (R6), and retained face/server/cloud scenarios with acceptance and gates (R7). It also made
roster hints and independent-producer/cost boundaries explicit. The matrix now accounts for the
photo-feature requests visible in the issue and conversation; it is not a claim to infer unspoken
requirements or to eliminate the following real choices.

Still open: real pilot album/number-source inventory; measured OCR engine/runtime/OS support and
accuracy; proven provider authorization and operational limits; any photographer delegation;
D1 face model/private format/consent/access/retention/release; D2 server capacity/publication; D3
whether a paid producer is needed. SPM authority is resolved, but its proposed identity round trip is not
implemented. The maintainer reviews these documents before tasks or application implementation.
