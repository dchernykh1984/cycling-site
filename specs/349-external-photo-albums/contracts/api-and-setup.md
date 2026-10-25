# API and visible setup contract (proposed)

Extend the existing gallery API/actions; exact route spelling can be finalized with implementation
tasks, while the operation set, permission parity and backward compatibility are requirements.
All machine routes remain under `/api/v1/`, without a language prefix.

## Operation and permission matrix

| Operation | Caller and bounds |
| --- | --- |
| Read enabled connector/index capabilities and guide links | A person allowed to open setup; no credentials/account grants returned |
| Classify/unclassify an existing material as a photo-album link | Authorized event manager/admin/owner; preserve source URL and other materials |
| Connect, inspect, refresh ("Refresh participants' tagging"), disconnect an external album | Manager of that album's event, or admin/owner; validated root and access |
| Mark a photo "this is me" / "not me", or clear the mark, in a registration album | An account that sees that registration album; the decision belongs to that registration only |
| Start/resume/finalize/cancel a photo upload and read its status | Event manager of the writable destination; capability/root checks, bounded job |
| Hide/remove or explicitly restore an indexed album/photo | Event manager/admin/owner; persistent publication decision, never deletes provider original |
| Read event albums, bib matches and paginated photos | Same event/album visibility as pages; 404 for non-visible resources |
| Read my registration albums, their matches and source-album facets | Authenticated account; registrations it filed, is the confirmed athlete of, or coaches (#315); never a caller-supplied account override |
| Request individual download or archive; inspect/cancel own job | Recheck resource visibility and job ownership; bounded selection and bytes |
| Stage/review/commit historical bib associations | Event manager/admin/owner; source preview, ambiguity and audit required |

Provider OAuth callbacks and authorization initiation are connection establishment, not a claim
that ordinary user authentication must be reimplemented through the API. Reuse the site's existing
member authentication and event management rules. Event upload tokens are for timing exchange,
not a blanket participant API credential.

API results include source/recognition/identity status and structured actionable errors, supported
versions, current limits and retry-after where relevant. Localized fields preserve ru/kk/en values;
numeric IDs, dates, paths and bibs are not translated. Both pages and API call the same actions.

The [user journey contract](user-journeys.md) fixes event/cabinet navigation, personal counts/covers,
guest return and selection semantics. Its cards/facets/statuses need API parity too.

## Album-link input: information beside the field

Before submission, show an always-visible compact explanation plus a reachable full guide:

1. **Supported now**: enabled/tested services and allowed link types; planned services separately.
2. **What is needed**: index filename/version, sample download, previews and required read access.
3. **How to prepare**: local indexer guide, tested version/download, operating systems and exact steps.
4. **What will happen**: local recognition, site metadata import, originals' location, public sharing
   effects, required grants and known material traffic/storage/cost limits.
5. **What is ready**: connection check, index state, processed/total counts, next action/retry.

This is a UI contract, not the final translated copy. No secret filename convention or undocumented
manual step may be required for success. Do not hide essential requirements in a tooltip, hover
state, a ticket or help that appears only after failure. Keep the compact help beside the input
on phones, with keyboard-accessible links. Sample, help and validator share version/capability data.

An unavailable local indexer has no fake download button or invented command. A feature depending
on it is not labelled ready until the tested tool and guide ship with the feature.

## Local guide contents

Installation and hardware/OS prerequisites; choose the album folder and keep original bytes;
configure optional roster/bib hints from existing authorized data; run/resume the tested command;
review candidate/false bibs; generate previews and publish files first, then manifest; connect or
refresh the site. Explain CPU time, progress, retries, incomplete results and correction publication.

For Dropbox synced folders, distinguish local files available offline from online-only placeholders;
a provider desktop client may download originals before indexing. Do not imply that metadata-only
sync supplies image bytes to OCR. Storage access is requested once per connection, with explicit
reconnection only when a grant expires or is revoked.

## Historical pilot surface

Named pilot events are 533 (Google Drive) and 719 (Dropbox); inspect their links later.
Choose the existing event, attach its old albums, show publication and number-search progress.
Show a separate indexed-photo-album section with these actions; keep additional materials for
videos, clips, documents and unclassified links. A manager explicitly classifies a photo link;
it can remain an ordinary external album before indexing. Retain the source and do not rewrite
or erase other materials; advertise number search only after a working import.
Offer manager import of old start/results files with a preview of proposed associations. Reuse the
existing event/registration facts; do not ask participants for names and bibs again to compensate
for dropped references. State separately how many photos are indexed and how many registrations
have confirmed issued numbers. Personal pages show missing association, pending indexing, no
accepted matches or unavailable media as distinct states, with the available next action.

## Delivery and outage behaviour

Metadata results still work while provider delivery is unavailable. Preview/original loads show
availability separately; do not render a broken-image icon as the only explanation. Safe delivery
uses the adapter's supported method and respects private access; cached assets cannot outlive an
access revocation. Archive requests pin their selection to photo/content revisions, recheck access
at execution and delivery, and report skipped/changed/unavailable files. They never expose tokens
or provider API credentials to a browser. Limits and expiry are visible before starting a job.

The [upload contract](uploads.md) covers the second organizer input path. Its transfer/resume/job
operations are required when the write-capable slice ships; a read-only connector is not a reason
to remove the product requirement or to advertise an unavailable upload button.

Future D1-D3 capabilities are listed as planned until they ship. Their query/enrollment/removal or
producer job operations require the same UI/API permission parity and visible status/cost rules;
the bib-only pilot does not expose inactive face controls or pretend server indexing is enabled.
