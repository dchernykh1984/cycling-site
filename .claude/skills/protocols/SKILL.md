---
name: protocols
description: Race protocols - how an uploaded results file is served, why it is sandboxed, what may and may not appear inside one, and the live-results loop. Read before touching protocols or the timing API.
---

# Protocols

A protocol is what the timing software uploads through the API by a token the event carries: an HTML
results file, a structured document, or both from one run. HTML alone is shown inside an iframe; a
document is drawn by the site itself.

## The structured document (issue #310)

- Schema: `protocols/document.py` (pydantic), exported to
  `protocols/schema/protocol-document-v1.json`; a test keeps the two equal. The generators
  (FinishProtocolGeneratorPython, StravaProtocolGenerator) keep a copy of that file and check their
  documents against it -- after changing the schema, copy it there too.
- The site knows no sport: sections, columns (label, `role`, `priority`, `group`, `toggle`), cells
  (`text`, `sub`, `url`, `strong`), rows (`group`, `status`, `note`), header/footer items, and the
  `groups` and `toggles` registries. A new column or header line is a generator change only.
- Compatibility: within schema 1 unknown fields are ignored and unknown section types drawn by their
  shape. A breaking change is schema 2; the site refuses a major it does not know, and an upload
  that also carried HTML falls back to it (`document_error`).
- `protocols/rendering.py` turns the stored document into what the templates draw;
  `protocol.css` / `protocol-doc.js` do the phone layout, search, group filter and toggles. The
  limits (FR-PRO-008) bound what one upload costs to draw -- keep the cell budget when adding parts.
- The upload switches a protocol in one transaction (event row locked, files written first under
  new names, displaced files deleted on commit).

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
