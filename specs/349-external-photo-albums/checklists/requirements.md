# Specification quality checklist

**Feature**: [spec.md](../spec.md) | **Checked**: 2026-10-25
**Scope**: Document quality, not proof of implemented behaviour or maintainer approval.

## Content quality

- [x] User stories describe value independently; historical Dropbox albums are the first pilot.
- [x] Spec states WHAT/WHY; technical choices and transport details live in plan/contracts.
- [x] Event/cabinet entry points, personal event cards and ordinary album links are distinct.
- [x] Reader-facing help is part of acceptance, including supported services and local indexing.
- [x] Existing and proposed behaviour are explicitly separated; originals and curated rights survive.

## Requirement completeness

- [x] Requirements and outcomes are testable; processing and uncertain identity have explicit states.
- [x] API, ru/kk/en, visibility, offline retries, compatibility and accessible setup are included.
- [x] SPM authority is confirmed by the maintainer; historical matching is reviewed, not guessed.
- [x] First pilot is bib-based; face/server/cloud wishes are retained with explicit decision gates.
- [x] Upload, manual precedence, roster hints and independent producer acceptance are explicit.
- [x] Pilot links and engine/access experiments are explicit inputs/gates, not fabricated results.

## Readiness

- [x] Research, logical model, contracts, sample, coverage matrix and acceptance runbook are present.
- [ ] Maintainer reviews and accepts the specification and architectural choices.
- [ ] Pilot sources/access and tested local tool/engine choices are verified before related tasks ship.

Open readiness items do not block review of the documents; they do block claiming the feature is
implemented or ready for users. No application implementation is authorized by this checklist.
