---
name: locations
description: The four-level geography tree behind every event - how to place an event, propose a venue, and avoid the duplicates that keep appearing. Read before creating or repointing any location.
---

# Locations

This file is ASCII like the rest of the repository, so the Russian and Kazakh names below are
transliterated. Read the real spelling off the database before typing one.

A `django-treebeard` MP tree, exactly four levels deep:

1. country
2. region
3. city (or village -- any settlement)
4. venue -- the actual start point

An event is always attached at **depth 4**. Every city carries a hidden catch-all venue -- "Drugaya
lokatsiya" / "Basqa oryn" / "Other location" -- for events whose start point is not known.

## Rules that keep the tree clean

- **A catch-all venue has no coordinates.** It inherits them from its city; giving it its own puts
  a pin in the wrong place and hides the fact that the start point is unknown.
- **A venue does have coordinates**, as exact as the announcement allows.
- Regions and cities carry coordinates too (about two thirds of them do).
- Use the helpers, not raw saves: `add_location_child`, `soft_delete_location`,
  `Location.propose_venue`, `get_or_create_other_location`. They hold the invariants -- path
  arithmetic, the mutation lock, the refusal to nest under a venue.

## Duplicates

The commonest damage. They appear when one place is written two ways: Oral and Uralsk are the same
city (Kazakh name and Russian name), Kaztalov and Kaztalovka the same village, and one region was
carrying a Kazakh letter inside its Russian name. Before creating anything, search all three name
columns for the place, and for what it is called in the other languages.

When you find a duplicate: repoint the events onto the surviving node, then delete the duplicate.
Deleting a city whose catch-all still exists needs the parent's `.delete()` (treebeard removes the
subtree); `soft_delete_location` refuses, on purpose, while anything hangs off it.

## Placing an event

Geography proposed by an agent arrives as `pending_approval` and waits for a human. An event may be
approved only when the geography *above* its venue is approved -- a freshly proposed venue under an
approved city is the designed flow.

Coordinates come from the announcement, from the first point of a linked GPS track, or from
Nominatim (one request per second, and send the project's own user agent). Never from memory: a
plausible-looking coordinate in the wrong valley is worse than none.
