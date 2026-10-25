# Portable photo index v1 (proposed)

The album contains `photo-index.v1.json` and referenced files. The producer publishes assets first,
then atomically replaces the index. This is the shared format for a local or future server producer.
See [example](../examples/photo-index.v1.json); example digests are illustrative, not real assets.

## Envelope

| Field | Rule |
| --- | --- |
| `schema_version` | Integer `1`; unknown major versions are rejected with supported-version help |
| `album_id` | Stable UUID owned by this album; independent of the provider |
| `revision` | Increasing integer, 1..2^63-1, durable across producer restarts |
| `generated_at` | ISO 8601 UTC timestamp; informational, not used to order concurrent revisions |
| `producer` | Tool name/version; optional OCR engine/model identifiers, no credentials |
| `bib_normalization` | `trim-nfc-exact-v1`; shared with the site and timing binding contract |
| `processing` | `inventory_complete` and `complete` booleans, `total`/`processed` nonnegative counts |
| `photos` | Full current known inventory, including pending/failed entries |
| `removed_photo_ids` | Explicit photo UUID tombstones; never inferred from a failed/partial scan |

No event ID in the file grants permission or attaches the album automatically. The authorized site
connection supplies the event. No account IDs, names, birth dates, emails, secrets or face vectors.

## Photo

`id` is a stable UUID within the album. `original` and `preview` each contain a safe relative `path`,
`sha256` (64 lowercase hex), `bytes` (positive integer) and `media_type` (JPEG/PNG/WebP). `preview`
may be absent while `processing_state` is pending/failed, but a searchable processed photo needs a
preview. Previews are separate derivatives without unnecessary metadata; originals stay unchanged.

`processing_state` is `pending`, `processed` or `failed`; `bibs` is an array, possibly empty.
Each observation has `value`, `state` (`candidate`, `accepted`, `rejected`), `method` (`ocr` or
`manual`), optional confidence in [0,1], and an optional correction reference. A manual change
records a local non-personal correction ID and prior value/state; the producer retains its audit.
OCR confidence is meaningful only for the named model, not comparable across different engines.

Normalize bibs by trimming boundary whitespace and Unicode NFC only. Keep leading zeroes,
letters and case. Values are 1..32 characters, without controls; no automatic `00120` -> `120`
conversion or OCR `O` -> `0` conversion. Alias rules, if needed for real data, require explicit
reviewed event configuration shared by indexing, timing and search, not separate heuristics.
Only accepted observations enter ordinary search. Candidate counts and an uncertainty-review
workflow remain visible to the manager. A photo can contain several accepted bibs.

The same photo UUID cannot occur twice, be both live and removed, or point at two originals.
Do not automatically merge distinct photographers' photographs by filename. A checked source move
retains IDs; a new photo's UUID is persisted by the producer rather than derived from its path.

## Revision and validation rules

A repeated revision with the same content digest is a no-op; the same revision with different
bytes is a conflict. Older revisions are rejected. Concurrent producers must coordinate one
revision sequence or stop with a conflict, not invent timestamp ordering.

`processed` equals the number of processed photo entries, `total` equals live inventory size,
and `complete` requires both `inventory_complete: true` and every live photo processed.
`inventory_complete` becomes true only after a successful full source inventory; a truncated or
interrupted scan keeps it false even if every discovered photo was processed. UI/API must expose
this flag and describe `total` as discovered photos until enumeration finishes. Failed entries
remain explicit and make processing incomplete. An unreadable bib is not a processing failure if the photo was examined.
A successor includes every prior live photo or explicitly tombstones it; an accidental omission
is rejected instead of implicitly deleting it. The first import may have an incomplete inventory,
and must encode `inventory_complete: false`, not only print a local warning. A complete producer
snapshot is not proof that OCR found every real bib; recognition quality is a separate measure.

Validate schema, field bounds, UTF-8, PostgreSQL-safe strings (including rejection of NUL), unique
IDs, safe paths and root membership before publication. Limit manifest bytes, photo count,
observations/photo, path length, decoded pixels and fetched asset bytes through named settings;
return the exact offending field/limit. No archive unpacking or arbitrary code in the index.
Do not require reading every original for metadata search or on every import: verify assets when
first fetched and invalidate mismatched delivery; manifest structural validation is not proof that
all external bytes are available or authentic. UI distinguishes indexed from media-verified.

Stage a new revision without changing the published pointer; commit projection and pointer
atomically. Known processed entries become searchable after a valid partial snapshot is published.
An outage during import keeps the old published snapshot. Unpublish/removal invalidates personal
results, cached delivery and queued archives, without deleting external files.

Site publication decisions are an independent overlay: producer tombstones update inventory,
while site hide/removal decisions still apply to every successor import. A newer manifest cannot
restore a site-removed photo/album. Keep minimal suppression identifiers and require an authorized
explicit restore; never infer restoration from the source file still being present.
