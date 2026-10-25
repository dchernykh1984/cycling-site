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
