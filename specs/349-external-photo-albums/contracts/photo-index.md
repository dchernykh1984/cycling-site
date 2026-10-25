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

Previews are a requirement on the album, not a site service: the producer writes them into the
album beside the originals, and the site never downloads originals to make thumbnails. The one
exception is an adapter that can produce a thumbnail itself (Dropbox's `files/get_thumbnail_v2`);
import rejects a processed photo that has neither, and names the entry. Whether album previews
stay mandatory for Dropbox albums is an open maintainer question. Maximum preview size (long side,
bytes) belongs to the format version, is shown in the setup help and is checked on first fetch;
the values are chosen from the pilot albums.

`processing_state` is `pending`, `processed` or `failed`; `bibs` is an array, possibly empty.
Each observation has `value`, `state` (`candidate`, `accepted`, `rejected`), `method` (`ocr`,
`appearance` or `manual`; an `appearance` observation is always a `candidate`), optional confidence in [0,1], an optional correction reference and an optional
`region`: the bib's box as `x`, `y`, `w`, `h` fractions of the preview in [0,1]. A region is not
personal data; it lets a later face slice pair a face with the bib and lets the viewer highlight it. A manual change
records a local non-personal correction ID and prior value/state; the producer retains its audit.
Manual observations include `content_sha256`, binding the decision to the reviewed original's
bytes. OCR confidence is meaningful only for the named model, not comparable across engines.

### Manual precedence during reindexing

For unchanged original bytes, the producer preserves manual observations and correction IDs when
resuming, changing OCR models or rebuilding the index. An explicit manual rejection of a value
cannot become accepted because OCR detects it again; a manual acceptance remains accepted.
Correcting a wrong value records its rejection and the replacement acceptance atomically, so the
wrong number does not return on the next pass. New automatic candidates may still be reviewed.

An optional photo-level `manual_review` contains `original_sha256`, `lock_accepted_set` and a
non-personal `review_id`. With `lock_accepted_set: true`, only the reviewed accepted set in `bibs`
is searchable; OCR may suggest candidates but cannot add accepted values. An empty reviewed set
is valid and survives reruns. Do not store a second accepted-number array in this object.

Only an explicit reviewer change/unlock alters a manual decision. If original bytes change,
retain the prior decision in audit, mark it stale for review and do not apply it to the new content
or erase it under the guise of a model update. A site import rejects manual observations whose
`content_sha256` or active review lock does not match that entry's original digest.


Normalize bibs by trimming boundary whitespace and Unicode NFC only. Keep leading zeroes,
letters and case. Values are 1..32 characters, without controls; no automatic `00120` -> `120`
conversion or OCR `O` -> `0` conversion. Alias rules, if needed for real data, require explicit
reviewed event configuration shared by indexing, timing and search, not separate heuristics.
Only accepted observations enter ordinary event search. A registration album also shows that
bib's candidates (uncertain OCR, `appearance`) for the participant to confirm or reject; candidate
counts and the review workflow remain visible to the manager. A photo can contain several
accepted bibs.

## Participant decisions are not part of the index

The site keeps two things apart (maintainer decision, 2026-10-25):

- its imported copy of the album's index, replaced only when an organizer adds the album or presses
  "Refresh participants' tagging" -- never by background polling;
- participants' decisions, per registration and photo: "this is me" (a green check) or "not me"
  (a red cross). They are site data, never written into the album, and survive every refresh.

That is also how a locally made index is validated. The site checks its structure on import --
schema, sizes, paths inside the album -- because those protect the site. It does not trust its
content: a wrong bib shows up as a candidate that the participant rejects, and a rebuilt or broken
index cannot erase what participants already decided. Producer-side corrections (manual precedence
above) stay in the index; they are the organizer's tool, not the participant's.

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
