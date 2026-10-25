# Document review log

**Scope**: Constitution amendment and issue #349 design, not implementation validation.
The shipping workflow calls for three self-review cycles; accepted findings get separate commits.

Reviews will check user requirements and existing behaviour, then cross-contract consistency,
then failure paths and readiness. This log records outcomes after those checks, not advance approval.

## Cycle 1 - Source and requirement validation

**Accepted finding R1**: A non-null registration `user` can be the submitter in free mode,
not the named athlete. Verified `registrations/views.py` sets both `user` and `registered_by`
while accepting free-form identity. Restricted automatic ownership to self-only, non-relay
entries and documented separate confirmation elsewhere, including the regression scenario.

**Result**: The design no longer treats this existing field as universal proof of athlete identity.
No application change is included.

## Cycle 2 - Cross-contract consistency

**Accepted finding R2**: `processed == total` could make an interrupted initial scan look like a
complete album, because the importer cannot see undiscovered files. Added machine-readable
`inventory_complete`, required it for `complete`, updated the sample/model and acceptance runbook.
A local diagnostic alone would not satisfy the transparent-setup principle.

**Result**: Readers can distinguish a complete inventory from only the discovered subset.

**Accepted finding R3**: The scope paragraph put event 533 before enabling its Drive connector,
while delivery slice 4 added that connector. Aligned the scope and acceptance order: Dropbox pilot
719 first, Drive pilot 533 once the Drive slice exists. No mandatory album relocation was added.
