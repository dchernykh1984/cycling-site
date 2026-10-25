# Validation guide: historical photo pilot

**Status**: Acceptance runbook for the proposed implementation. Photo-specific commands/routes and
an indexer do not exist yet; this document does not claim that these scenarios can run today.
Use the contracts as acceptance inputs when generating implementation tasks after review.

## Prerequisites

Start with event 719 (Dropbox), then event 533 (Google Drive); an optional third event can follow.
Inspect album links in additional materials during the pilot and obtain owner-approved read
access. Include one event with several photographers' albums. Collect retained SPM/start/results
files where available.
Select a manager-reviewed labelled sample including several people/bibs, leading zeroes, blur and
unreadable numbers. Record real counts rather than assuming storage or CPU capacity.

## 1. Validate the documents now

From the feature worktree, check the sample parses:

```bash
python3 -m json.tool specs/349-external-photo-albums/examples/photo-index.v1.json > /dev/null
pre-commit run --all-files
```

The example's zero/one digests illustrate field shape; they do not verify real files. This is a
JSON syntax check, not schema/connector/accuracy validation. Current work adds no runtime behaviour.

## 2. Produce and import a real pilot album after implementation

Use the tested local-tool command linked beside the album input. Materialize synced originals,
index a sample on CPU, inspect uncertain observations, and publish previews plus a final manifest.
Connect the existing event and album; request import through UI and the equivalent API operation.

Expected: stable photo IDs, retained original bytes, progress and accepted-bib matches. Interrupt
and resume indexing/import; repeat a revision; submit an older/conflicting revision; disconnect
storage during search. Metadata remains queryable from the last valid authorized published index;
media availability is separately reported. Stop source enumeration before it discovers every
photo while processing all discovered ones: the UI must still say the inventory is incomplete. Missing/photos pending are not reported as "no rider".

Run the same conformance fixture through Dropbox, Drive and HTTPS adapters. Include duplicate
Drive path names, foreign-root references, revoked access, 429 and changed content. Prove no
provider call happens in metadata search, including personal galleries and pagination.

## 3. Validate historical identity and future number round trips

Import a retained number file; compare names only as suggestions. Confirm reviewed mappings,
leave equal-name/absent/relay rows unresolved and re-import idempotently. An account that entered
another person must not receive their photos as its own, even when both registration `user` and
`registered_by` point to that account. Record original source and reviewer.

For a future race, import registrations into SPM, assign/edit bibs, save a backup and restart.
Send legacy lines plus structured bindings; require capability advertisement and revision ACK.
Verify own photos without another bib input. Test duplicate bibs across devices, corrections,
withdrawal, foreign event IDs, stale/offline retries and old-client uploads without bindings.

Expected: no guessed identity, no silent overwrite, legacy exchange unchanged, explicit conflict
or stale status and a safe resync path. The site can associate before a finish protocol exists.

## 4. Verify the user-visible contract and evidence

Exercise ru/kk/en, phone, keyboard and API permission parity. At the album field verify supported
services, scope, format version, sample, tested tool guide and next-action errors. Test a first-time
manager using only that help. Test hidden/invite-only events, cross-manager ownership, private
previews and archive owner/access revocation. Remove a photo on the site, re-import a newer
manifest still containing it and retry a prepared archive: the photo must remain unavailable until
an explicit authorized restoration. Curated gallery permissions remain unchanged.

Record pilot precision/recall, unreadable rate, CPU time, import memory, metadata query p95,
external traffic, original integrity and download failures. Evaluate the 10,000-photo search fixture
separately from actual pilot size. Bulk archives must stay within advertised byte/photo/TTL bounds.

Site implementation validation uses `.venv/bin/python -m pytest -n 10 -q --ignore=tests/e2e`,
applicable `tests/e2e/` Playwright scenarios, pre-commit and the complete exact-head CI rollup.
Desktop validation belongs to its repository and must pin the actual commit tested. This docs-only
PR needs document checks and its own CI, not invented feature tests or paid provider operations.
