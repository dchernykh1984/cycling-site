# Feature Specification: A knockout drawn as a ladder

**Issue**: #454
**Status**: Built
**Decided with the maintainer**: 2026-11-07, in conversation; recorded here

## Scope

The finals of a knockout -- heats of a few riders, the first places of each going on to the next
round -- reached the site as one column of tables, the final first. On a desktop that hides what a
knockout is about: which heat fed which. The generator's own HTML draws the ladder, but in its own
look, in a frame, without the search and the category filter. A structured protocol may now hold a
section that says it is a ladder, and the site draws it as one.

## Decisions

1. **The data.** A section of type `ladder` holds the stages of one knockout as its sections, in the
   order they are ridden, and each stage holds the tables of its heats. No new field: the schema
   stays 1 and only the type's value is new; a site that does not know it draws the same tables by
   their shape. The site knows no sport: any knockout fits.
2. **A desktop** (from 992px, the site's switch to the desktop layout) sets the stages side by side,
   the first on the left. A stage's heats share its height evenly, so each heat sits level with the
   middle of the two before it, and thin lines join them where every heat was fed by exactly two.
   A stage with as many heats as the one before -- a final and a race for third place -- stands its
   heats together in the middle, without lines.
3. **A heat nobody is seated in yet** is sent all the same and drawn as an empty box, so the ladder
   keeps its shape; a phone leaves it out, and a stage of nothing but such heats too.
4. **Columns.** Each table shows what fits its column by the protocol's own priorities, exactly as a
   table fits its box today; the place and the name, priority 1, always stay. The rest opens on a
   tap on the row or with "All columns". When even those do not fit, the ladder scrolls sideways
   inside its box, never the page. A ladder's tables are set as tight as a phone's.
5. **The finals' time** matters less than in a timed race: the generator gives it a priority of its
   own, after the year, the city and the team and before the number, so a narrow column keeps the
   place and the name.
6. **A phone** lists the stages, the last first -- the final on top -- each under its name.
7. **A heat named as its stage** ("Final" in the stage "Final") does not repeat the name above its
   table; its table still carries it for a screen reader.
8. **Search, the category filter and live updates** work as in any protocol. A search keeps every
   stage of a ladder in its place, takes away the heats it empties, and the lines while it is on.

## The generator

FinishProtocolGeneratorPython sends its finals this way; only the data for the site changes, its
own HTML protocol is untouched. Should the ladder not suit a meeting, the generator's protocol
format set to "HTML" shows the HTML as before.

## Not built

- A layout chosen by hand, or a race for third place in a column of its own.
- Ladders inside other sections: a ladder is a section of its own, three levels deep with its
  stages and heats (FR-PRO-008).
