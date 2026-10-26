# Connector contract v1 (proposed)

The core calls an adapter selected by registry key. Provider branches belong inside adapters.
Every enabled adapter supplies localized setup metadata from the same capability definitions.

## Required read operations

| Operation | Input | Output / guarantee |
| --- | --- | --- |
| `capabilities` | Authorized connection, bounded root | Read/preview/download modes, limits, optional write/change features |
| `stat_manifest` | Root, configured manifest name | Exists, opaque version/validator, size; no recursive scan required |
| `read_manifest` | Root, expected provider version | Bounded bytes and actual version; change during read causes retry |
| `resolve_asset` | Safe relative path, expected SHA-256 | Unique object, verified root membership, internal native ID/version |
| `open_asset` | Resolved reference, original or preview | Bounded stream/metadata, or normalized access/availability error |

Optional capabilities: change cursor, provider preview generation, safe browser delivery,
file upload and manifest publication. Read-only sources do not need any write grant. The core
never assumes that every provider has an archive endpoint or a stable public URL.

The portable root is a logical folder. OAuth scope is a different control; describe the provider's
real grant even when the site enforces a narrower root. Existing Drive folders may need a different
route from `drive.file`; Dropbox App Folder does not cover arbitrary personal folders.

## Site-hosted storage

The site's own storage (its media disk, or an object store it controls) is one more adapter with
the same operations, not a separate code path. Moving an album onto the site later means copying
the folder and switching the album to that connection through a verified source move: photo IDs,
relative paths, manual decisions and the event link stay as they are, and the index format does
not change. The existing curated gallery keeps its current storage and is not migrated by this.

## Write-capable slice

Adapter capabilities remain optional, but the product must support the site's upload workflow
through enabled writable adapters. Implement authorize/start, append/resume, finalize, inspect and
cancel as needed for the provider's transfer protocol, following the [upload contract](uploads.md).
Read-only adapters explicitly lack this capability and continue to support ready album imports.

## Path and asset rules

Paths are UTF-8 NFC, relative to root, case-sensitive logical names. Reject absolute paths, URI
schemes, empty/dot/dot-dot segments, backslashes, NUL/control characters and encoded traversal.
Adapters may decode a submitted provider link only at the boundary; path strings are not arbitrary
URLs. Require exactly one result per segment; Drive duplicate names produce `ambiguous-path`.
Reject provider shortcuts/symlinks in v1 instead of escaping or silently changing the root.

A move/rename cache hit is rechecked against root membership and content identity before serving.
Native IDs and opaque revisions are private adapter details. Never cache temporary URLs as portable
asset references. Use a provider-supported safe delivery mode or a bounded authenticated proxy;
never assume a temporary API URL may be embedded in a browser.

Delivery (maintainer decision 2026-10-25; see [research section 7](../research.md)):

- **Reading needs no token from the organizer.** The site uses its own Dropbox app ("app
  authentication", App key and secret). Dropbox documents app authentication for
  `files/list_folder` with a `shared_link` and for `sharing/get_shared_link_file`; for
  `files/get_thumbnail_v2` with a link resource Dropbox staff confirm it. A folder shared "anyone
  with the link" is all the site needs.
- **Per-file links come from the indexer.** Dropbox's API cannot link to one file inside someone
  else's shared folder, and its scopes limit kinds of operations, not folders: the narrowest grant
  is an App-folder app that sees only `/Apps/<app name>`. So the site never asks organizers for a
  token. The indexer, running on the organizer's computer under the organizer's own Dropbox
  login, may create a shared link per file and write it into the index as `view_url`; that login
  never leaves the computer.
- **Thumbnails**: when the index gives a preview's `view_url`, the page shows it straight from
  Dropbox (`raw=1`) and the site stores nothing (pending the embed check). Otherwise the site keeps
  a tiny thumbnail, about 10-20 KB (a long side of about 320 px), made with
  `files/get_thumbnail_v2`; 2,000 photos are roughly 20-40 MB of disk (estimate). Rules for those:
  - stored outside `MEDIA_ROOT`, because `serve_media` hands out any file under it without a
    permission check; served only by a view that applies the album's visibility, with
    `Cache-Control: private` and a short lifetime, so no shared cache keeps a thumbnail of an album
    that has since been hidden;
  - named by the site's internal album and photo IDs plus the source digest, never by UUIDs taken
    from an index; the URL carries the digest, so a changed preview or original gets a new
    thumbnail, the old file is deleted after the import commits, and a thumbnail made from an old
    digest is never attached to the new one;
  - Dropbox does not make thumbnails of files over 20 MB: a processed photo with no preview and an
    original over that size is listed to the organizer as "needs a preview" with its path and the
    fix (run the indexer with previews); readers see a neutral placeholder and can still open the
    photo in Dropbox.
- **A click opens the photo in Dropbox in a new tab**, so viewing and downloading use Dropbox's
  traffic: the original's `view_url` when the index has one, otherwise the folder link with
  `preview=<file name>` (what Dropbox's own page produces when a file is clicked; undocumented,
  so the pilot confirms it), otherwise the folder link itself.
- No proxy of originals through the site in the first slice; archives come later.

The HTTPS adapter confines every path and redirect to configured public origins/root. Protect
against SSRF including DNS resolution, redirects, private/reserved network addresses and oversized
responses. A provider adapter accepts only its known URL shapes/API hosts, never arbitrary fetches
using its credentials. Do not log token-bearing links.

## Errors and retries

Normalize `unsupported`, `reconnect-required`, `forbidden`, `not-found`, `ambiguous-path`,
`changed-during-read`, `throttled` (with retry-after), `invalid-data`, and `unavailable`.
Retry only retryable states, with bounded backoff and saved cursor. A failure is not an empty album
and cannot broaden sharing or remove the last good index. Explain next action through the UI/API.

## Conformance

Run the same fake-source fixtures through Dropbox, Drive and HTTPS adapters: valid/missing index,
partial changes, duplicate path, expiry, 403/404/429, changed version, traversal, foreign root,
content mismatch and interrupted stream. Assert no provider calls during metadata searches.
Real-account tests are opt-in and read-only unless upload testing is explicitly scoped.

Adding Yandex or another adapter must pass these tests and document actual scope, ID/version,
sharing and delivery semantics before being marked supported. A registry entry alone is not support.
