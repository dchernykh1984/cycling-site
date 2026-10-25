# Organizer uploads to connected storage (proposed)

This is the second input path, alongside connecting a ready externally indexed album. It is a
product requirement, not merely an optional adapter method. It may follow the read-only pilot;
the feature is not complete until this path has its UI/API, tests and visible operating limits.

## User flow and boundaries

An authorized event manager chooses their event and an existing writable connection/root, then
selects files and starts upload. Reuse known event, title and connection facts rather than asking
for credentials or an event again. Each organizer can manage their own event albums; ownership of
one connection does not grant access to another organizer's files. A delegated photographer role
can be designed later; it is not a new blanket upload right for every participant.

Show per-file/total progress, accepted types and byte/count limits before submission. Read-only
albums remain connectable; explain missing write permission and the alternatives (use another
writable connection or upload externally), not an unexplained disabled control.

The server authorizes upload and keeps long-lived provider credentials private. Use a provider-
supported narrowly authorized upload session or bounded server forwarding/staging; do not give a
browser the connection's reusable token. Durable originals end up in the selected external root,
unchanged. Temporary site staging has explicit size/expiry/cleanup rules and is not another
permanent photo library. Validate file type, decoded-image bounds, total bytes and safe names.

## Retry, completion and indexing

Persist the upload job and per-file identity/checksum/provider session state. Retry/resume only
unfinished files; accepted files survive a partial failure and do not become duplicates on resend.
Do not silently overwrite an existing path or choose an arbitrary duplicate name. Allocate a
unique safe asset reference and preserve the original filename as metadata where appropriate.
Expired upload sessions show a recoverable per-file error; no instruction asks the organizer to
re-enter event/profile facts. A browser may require reselecting a local file after restart; say
which unfinished file is needed, while retaining confirmed remote uploads and the rest of the job.

Uploading originals does not itself mean they have been indexed. With a local producer, show the
uploaded files as awaiting indexing and link to the guide for materializing/syncing that album on
the local computer, running the producer and publishing previews/index. With a separately enabled
background producer, enqueue bounded indexing work. Import only committed manifest revisions;
partial results become available as valid revisions arrive, with progress and next action.

Only one authorized producer owns the manifest revision sequence at a time. Site upload and a
local indexer coordinate new assets through the same inventory/identity rules; neither silently
replaces manual corrections or publishes a partially written manifest. Cancellation does not
remove previously published originals or unrelated files. Explain whether staged/unpublished
files remain in the selected external folder and offer an explicit authorized cleanup action.

## API and acceptance

The API provides upload capability/limit discovery, job initiation, transfer/resume, finalization,
status and cancellation with the same event ownership and root checks as the page. Different
provider transfer protocols stay behind the adapter, not in gallery search or account matching.

Validate two organizers with separate roots, read-only access, oversized/invalid files, an
interrupted batch with some accepted files, repeated finalize, expired sessions, safe collisions,
revoked access and cancellation. Demonstrate that completed files are not uploaded twice and are
not labelled searchable before an accepted index revision. All tests are future acceptance checks;
this PR implements no upload endpoint or worker.
