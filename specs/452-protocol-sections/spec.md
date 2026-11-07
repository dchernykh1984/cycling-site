# Feature Specification: Protocol sections

**Issue**: #452
**Status**: Built
**Decided with the maintainer**: 2026-11-07, in conversation; recorded here

## Scope

An event had one block of protocols, "Protocols", and at most one protocol of each type (absolute and
group). The finals published with the event's token replaced the qualification's protocols, and the
stages of a cup published by StravaProtocolGenerator replaced each other. Several tokens per event
were weighed and set aside: the token stays one, and the protocols are split into sections.

## Decisions

1. **Sections.** An event's protocols are shown in sections, each under a heading of its own, in the
   order of their numbers. Section 1 is every event's: without a name it is called "Protocols" in the
   page's language, as before. A section without protocols is not shown to readers.
2. **Names.** The organizer -- whoever sees the event's upload token: its author and its managers --
   adds sections on a page of their own, linked from the token's block. A name is required in every
   language of the site. Section 1 may be renamed the same way, never deleted.
3. **Numbers.** A new section gets the next number the event never had: a deleted section's number
   is not given again, so software still set to it is refused rather than filling another section.
4. **Deleting.** A section holding protocols is not deleted: the protocols are deleted first, from the
   generator, with the section's number.
5. **Publishing.** The protocol generators send the section's number (`section`) with an upload and
   with a delete; without it a protocol goes to section 1, so software that does not know sections
   works as before. A section the event does not have is a 400 that says so. An event holds one
   protocol of each type per section.
6. **Only protocols.** Start lists, timings and the live stats for watches stay one per event.
7. **A protocol's page** names its section, when the organizer named it, in the trail above the
   results and in the title a link previews with.
8. **The API** lists, adds, renames and deletes an event's sections for the same people, with the
   same rules (`/api/v1/protocols/competitions/{id}/sections`).

## The generators

StravaProtocolGenerator sends a section for the overall cup and for each stage, and
FinishProtocolGenerator for its run. StartProtocolMaker and the chronometers neither upload nor
delete protocols and are unchanged.

## Not built

- Several upload tokens per event, or start lists and timings kept apart by section.
- Reordering sections other than by number.
