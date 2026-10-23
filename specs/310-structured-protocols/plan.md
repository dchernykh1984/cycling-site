# Implementation Plan: Protocols as data

**Branch**: `310-structured-protocols` | **Spec**: [spec.md](spec.md)

## Summary

A versioned, self-describing JSON document next to the protocol's HTML; the site validates it,
stores it and draws it; the generators build it from the same calculations as their HTML.

## Technical Context

Django 6, django-ninja (pydantic) for the schema, PostgreSQL JSON column, plain JavaScript.
Generators: FinishProtocolGeneratorPython and StravaProtocolGenerator (PySide6, uv), separate
repositories and pull requests.

## Constitution Check

- I (facts): the document carries only what the generator computed; nothing is parsed out of old HTML.
- III (tests): unit, upload failure and concurrency, e2e on phone and desktop, in every skin.
- IV (languages): a protocol document belongs to one language (`lang`); recorded as an exception in
  specs/site/protocols.md.
- VI (no sport hardcoding): roles are generic (place, bib, name, result, gap, group, team); laps,
  attempts and splits are plain columns with groups and toggles.

## Design

- Phase A0 (separate pull request): the live loop confirms what it shows (FR-PRO-005).
- Model: `Protocol.document`, `ProtocolVersion.document` (nullable JSON); `html_file` optional.
- Upload: one endpoint, `html_file` and/or `document`; validated before anything is written; files
  first, then one transaction with the event row locked; displaced files deleted on commit.
- Schema: `protocols/document.py`, exported JSON Schema, limits and a cell budget.
- Drawing: `protocols/rendering.py`, templates `_document.html`, `_section.html`, `_table.html`,
  `_item.html`, `protocol.css`, `protocol-doc.js`; live swap through `protocols/<pk>/fragment/`.
- Generators: build the document from the functions their HTML writers use (FPG first makes those
  functions pure without changing a byte of HTML), send it with the HTML.

## Out of scope

Eliminator Finals (not implemented in the generator); labels in three languages; numeric values and
sorting; parsing old HTML; re-uploading old protocols on production (needs the maintainer, per protocol).
