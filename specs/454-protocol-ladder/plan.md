# Implementation Plan: A knockout drawn as a ladder

**Spec**: [spec.md](spec.md) | **Issue**: #454 | **Branch**: `454-protocol-ladder`

## Approach

- **`protocols/rendering.py`** recognises a section of type `ladder` that has the shape -- stages
  holding the tables of their heats, nothing deeper, no table of its own; anything else stays drawn
  by its shape (FR-PRO-007). It keeps a heat without rows as `vacant` (FR-PRO-012 otherwise drops
  it), drops a ladder with no rider at all, and marks the stages: `feeds`/`fed` where a stage has
  twice the heats of the next, `together` where it has as many. The ladder keeps the section shape
  the rest of the module walks (`table`, `sections`), so the category chips, the column chips and
  the row numbering need nothing new.
- **`protocols/_ladder.html`**, included by `_section.html`, writes the stages in riding order: a
  slot per heat (the lines hang on it), the heat's `.protocol-section` inside (search and fitting
  act on it as on any table), an empty box for a vacant heat.
- **`protocol.css`** does the rest, with no script: a column (`column-reverse`) on a phone, a row
  from 992px with `flex: 1 1 0` slots, the lines as borders in the gaps, an inner sideways scroll
  when the stages' minimum width does not fit. Colours are the skin's own variables.
- **`protocol-doc.js`** only marks a search in progress (`protocol-searching`), when the lines go:
  `fitColumns` already measures every table in its own box, so a ladder's narrow columns leave out
  the low priorities first.
- **The generator** (FinishProtocolGeneratorPython, a pull request of its own) builds one ladder per
  group from the heats of every stage, empty ones included, and gives a heat's time priority 4.

## Constitution Check

- **II (the maintainer's decisions)**: the look of light and dark changes only by the new layout the
  maintainer asked for; nothing existing is restyled.
- **III (tests)**: unit tests for the shape and the flags; browser tests for the desktop ladder, the
  phone list, the narrow column, the search, the category filter and legibility in every skin.
- **VI (anyone, anywhere)**: no sport, round or place name in the code -- the type is `ladder`, the
  names come from the document.
- **VII / XI (API)**: protocols arrive through the API already; reading them stays an API gap
  listed in `specs/site/protocols.md`. The schema's version does not change.
- **XII (any screen)**: phone first; the page never scrolls sideways; text keeps 4.5:1 in every
  skin (`test_the_stage_and_heat_names_stay_legible_in_every_skin`).

## Tests

- `tests/test_protocol_document.py`: the ladder's stages, its vacant heats and flags, a ladder with
  nobody seated, look-alikes drawn by their shape, the group passed down, the page's markup.
- `tests/e2e/test_protocol_ladder.py`: side by side on a desktop with the final level between its
  semi-finals; the final first on a phone; vacant heats; a five-round ladder that keeps place and
  name and scrolls inside its box; a search that leaves the stages in place; the category filter;
  legibility in every skin.
