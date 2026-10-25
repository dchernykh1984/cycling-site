# Issued bib exchange v1 (proposed optional extension)

Existing `/api/v1/participants/` supplies each registration `id` and its `competition_id`.
StartProtocolMaker must retain these references when importing and assigning bibs. Existing
`/api/v1/start-list/` transport, authentication, legacy `items` and revision counter remain.
This contract is a proposal: these binding fields are not implemented today.

## Optional envelope addition

An upgraded POST may add `registration_bindings` beside existing fields:

```json
{
  "schema_version": 1,
  "site_origin": "https://example.org",
  "competition_id": 42,
  "entries": [
    {
      "entry_id": "c0ee56da-2a9e-4543-8ef1-21465819e214",
      "registration_id": 1234,
      "line_index": 0,
      "bib": "120",
      "state": "assigned"
    }
  ]
}
```

The example is the value of the new field, not a replacement POST body. The existing
`competition_token`, `device_id`, `client_revision` and `items` stay required as before.
The token authorizes the event; origin/event/registration references confer no permission.

`entry_id` is a durable local entrant UUID; `registration_id` may be null for an on-the-day entrant
not yet linked to a site registration. A name is not a substitute. Assigned entries reference a
unique zero-based `line_index` whose legacy bib agrees with the structured bib. Withdrawn entries
have `state: "withdrawn"`, null bib and null line index. Preserve their entry ID for audit.

Use `trim-nfc-exact-v1` bib normalization from the photo-index contract. Validate bounded IDs,
values, list size and total request bytes within the existing endpoint limits. Reject foreign
events, missing/deleted registrations, duplicate assignments and inconsistent line references;
none is a reason to bind by name. Relay entries bind the registered team, not inferred member accounts.

## Snapshot and conflict semantics

- One full bindings snapshot belongs to the same per-device `client_revision` as its `items`.
  Validate and store both atomically. Equality/idempotency compares both, not just legacy lines.
- Older revisions receive 409; identical retries are no-ops; equal revisions with changed lines
  or changed bindings receive 409. GET exposes current per-device revisions and structured data
  only to the same event-token-authorized timing callers.
- Enforce active bib/registration uniqueness across devices under an event-level lock. A valid
  newer conflicting proposal receives 409 and a manager-visible dispute; it does not overwrite
  the last accepted snapshot. Disputed personal associations are suspended pending resolution.
  An invalid or stale request cannot by itself mark an accepted association disputed.
- Reassignment/releasing a number is explicit. Manager resolution records competing sources and
  changes affected device projections atomically or instructs the owning devices to resubmit.
  Reconnecting a stale device cannot silently reclaim the number. History survives corrections.
- Removing a prior entrant from an explicit full snapshot withdraws that device's assignment.
  Cross-device transfer requires a reviewed/authorized transfer, not last-writer-wins ordering.

## Capability acknowledgement and older clients

GET adds `start_list_capabilities.registration_bindings_versions: [1]` when supported. A POST that
accepts bindings returns `registration_bindings_revision` equal to the accepted `client_revision`.
New clients require both advertised support and acknowledgement; HTTP 200 from an older server
that ignores unknown fields must not be reported as successful identity synchronization.

Older clients may keep sending only `items`, and old consumers may ignore new GET fields. A newer
legacy-only snapshot keeps start-list exchange functional, but marks that device's earlier binding
projection stale. Preserve historical facts; do not silently keep using an unverified mapping for
personal photos and do not treat field absence as a confirmed mass withdrawal. Return the stale
state for the manager and request a capable-client resync. Replaying the exact older legacy-only
revision remains an idempotent legacy retry.

Do not append a positional field, replace comment contents or alter the meaning of existing
`competitor_id` (currently the bib). New support lives in structured metadata. Mixed-version tests
must prove the existing server/client responses retain their prior meaning.

## Desktop persistence and offline transfer

The imported reference is part of the local entrant model, not recoverable from display name.
Preserve it through Merge/Replace, bib edits, sorting, backups, saved projects, restart and resend.
A local file export can include a versioned sidecar containing this same envelope plus its source
revision and a digest of the associated legacy file; a mismatch is an explicit stale-sidecar error.
FinishProtocolGenerator may consume/forward the metadata beside unchanged lines; it does not
invent registration links from `competitor_id` or HTML cells. No new finish document is required
for site photos once the start-list assignment has been acknowledged.

## Historical backfill

Import retained SPM data first; use start/results number rows when no linked SPM record survives.
Stage row source, file digest, event, bib and candidate existing registration; show the original
facts and conflicts to an authorized manager. Name/birth/category similarity suggests a candidate
but never commits identity automatically. One confirmation can apply an unambiguous reviewed batch;
ambiguous or absent entries remain unresolved. Do not require old athletes to re-register.

Only an existing athlete-owned registration or separately confirmed athlete link enables personal
photos. Registered-by is insufficient; absent accounts and relay members remain event-level bib
search only. Keep history, reviewer and corrections. Historical proposals cannot replace a newer
SPM-confirmed assignment without explicit manager resolution. Expose source/status in manager UI.
