---
name: protocols
description: Race protocols - how an uploaded results file is served, why it is sandboxed, what may and may not appear inside one, and the live-results loop. Read before touching protocols or the timing API.
---

# Protocols

A protocol is an HTML results file produced by the timing software and uploaded through the API by
a token the event carries. The site shows it on the event's page, inside an iframe.

## It is somebody else's HTML on our domain

So it is served under a deliberately narrow policy (`protocols/views.py`): `default-src 'none'`,
`sandbox allow-scripts` without `allow-same-origin`, inline script and style only, no frames, no
forms, no connections. Regexes strip `<script src>`, `<base>` and meta-refresh as well.

Consequences worth knowing before promising anything:

- **Images.** `img-src` allows `data:` and the site's own origin, the latter built from the request
  so every deployment allows its own address and no other. `'self'` cannot do that job here: with
  `sandbox` and no `allow-same-origin` the document's origin is opaque and matches nothing.
- **Anything external stays blocked**, deliberately: a file we did not write must not be able to
  call home or count who opened it.
- **Give every image `width` and `height`.** The iframe measures the document once, on load, and a
  picture that arrives afterwards is not an event it re-measures -- without the attributes the
  browser reserves no space and the bottom of the protocol is cut off.

## Live results

A protocol marked live is polled by the page (`protocols/static/protocols/protocol-live.js`):
`/api/protocols/<pk>/last_updated/` returns the file hash, the live flag and the form it is shown
in. That answer is only a hint. A newer upload is loaded into a second, hidden frame, and the
script `protocol_html` injects into every file reports back the hash, live flag and form of the row
the file was read from (`protocol_state`). Only that report swaps the frame and ends live -- an
upload landing between the two requests would otherwise be shown under the other one's flag, and a
frame's `load` event fires for an error page too. No report within `PROTOCOL_LOAD_TIMEOUT_MS`
keeps the old protocol on screen and retries next round, even when the hint said "final".
The polling URL is built with `{% url %}`, so it carries the language prefix like every other
reader-facing address.

## Versions

Each upload keeps the previous file as a `ProtocolVersion`, and the detail page lists the update
history. Ten versions are kept.
