# Issued bib exchange v1 (proposed)

Existing `/api/v1/participants/` supplies each registration `id` and its `competition_id`.
StartProtocolMaker (SPM) loses that `id` today: `participant_to_open_line()` builds
`number#name#group#laps#stage#year#team#city#comment#time_shift#` without it. This contract keeps
the reference with the line, so the issued bib and the entry it belongs to travel together
through text files, backups, FTP and the existing `/api/v1/start-list/` upload.

**Decision pending (maintainer)**: variant A below is recommended; variant B is the alternative.
Neither is implemented today.

## Variant A (recommended): a trailing entry-reference field

One optional field after the start delay, the eleventh field (index 10):

```
120#Ivanov Ivan#M40#3#1#1984#Team#Almaty##0 00:00:00.000#r1234#
12#Petrov P<BR>Sidorov S#Relay#3#1#1980<BR>1985#Team#Almaty<BR>Almaty##0 00:00:00.000#r2051#
15#Kim A / Lee B#Relay#3#1#1990 / 1992#Team#Almaty##0 00:00:00.000#r2101,r2117#
7#Late Entrant#M40#3#1#1979###0 00:00:00.000##
```

- **Grammar**: empty, or comma-separated tokens; v1 defines one token kind, `r` followed by the
  site registration ID in decimal (`r1234`). No spaces, `#` or line breaks. A reader skips a token
  kind it does not know, so a later kind can be added without breaking v1 readers.
- **One registration, one token**. A relay registered on the site as one team entry is one token
  (its members are strings in that registration). A team assembled in SPM from separate
  registrations ("Add into team") carries one token per member, in member order.
- **No token** means an entrant without a site entry (on-the-day, typed by hand, an old file).
  Their bib stays searchable at event level; it is never bound by name.
- **Scope**: a token means "registration N of the event whose token delivered this line". The site
  checks every token against that event; a foreign, deleted or rejected registration is ignored with
  a manager-visible warning. A token grants no permission.

### Why a registration ID and not the account ID

The account ID was considered first. It answers the wrong question in these cases:

- One account files several entries for one race (`allow_multiple_registrations`, or a parent
  entering a child and themselves). The account ID cannot say which bib belongs to which entry.
- In free mode `user` and `registered_by` both name the submitter, not the athlete
  (`registrations/views.py`), so the account ID would hand the athlete's photos to the submitter.
- A relay line is several people; one account ID cannot describe it.
- An on-the-day entrant has no account at all.
- A line in a start protocol file is copied, uploaded by FTP and printed. An account ID there is a
  site-wide identifier of a person; a registration ID only means something inside one event.

Who the athlete of a registration is stays a site fact (see [data model](../data-model.md)),
so it can be confirmed or corrected later without rewriting any start protocol.

### Readers that already exist

Verified on 2026-10-25:

- FinishProtocolGeneratorPython reads fields by index (`get_field`, `StartProtocolElement.from_line`)
  and has ignored anything past field 9 since its first Python release (`9aece9f`).
- WindowsChronometerPython reads only field 0 of a start line.
- The site stores uploaded start-list lines as opaque strings (`StartListUpload.items`) and returns
  them unchanged to FPG; each line may be 2000 characters, far above a few tokens.
- An older SPM Python keeps loaded lines verbatim and drops the field only when a line is rebuilt
  from its form; the site handles that loss as described below.

The C++ tools are unmaintained and out of scope (maintainer, 2026-10-25).

### What SPM does

- Import from the site writes `r<id>` into the open-list line.
- Opening a line in the form keeps its tokens as form state; saving or editing the line writes them
  back, including after a bib, name or group change. The form shows that the line is linked to a
  site entry and offers an explicit unlink. A cleared form starts without tokens.
- "Add into team" appends the added entrant's tokens to the team line.
- Merge from site matches an existing line by token first, then by the current name/year key, so a
  registration renamed on the site does not come back as a second line.
- The same token on two protocol lines is reported like a duplicate bib.
- Backups and the start protocol file hold the lines as they are; no second file is written.

### What the site does with an upload

Derive assignments from the accepted snapshot of every device, under the existing event lock:

- A token on a line with a bib in field 0 assigns that bib to that registration. An empty field 0
  and SPM's `NOT_PAID` marker assign nothing; letters and leading zeroes are ordinary bib text.
- Several tokens on one line give every listed registration the same bib (a team).
- The same registration with two bibs, or one bib on two lines with different tokens, is a conflict:
  personal matching for those entries is suspended and the manager sees both sources. No winner is
  guessed; the last upload does not silently win.
- A bib bound in the previous snapshot that is still present but has lost its token (edited in an
  older SPM) keeps its binding, marked for manager review. A bib that disappeared withdraws it.
- History of assignments, corrections and their sources is kept.

FPG may later carry the tokens into the protocol document as non-displayed row data, so results
can be linked to accounts too. Photos do not need that: the start-list upload already says which
bib went to which entry, before any finish protocol exists.

## Variant B (alternative): structured bindings beside unchanged lines

Leave every line as it is and add `registration_bindings` to the start-list POST: per entrant a
durable local UUID, `registration_id`, `line_index`, `bib` and `state`, under the same
`client_revision`. GET advertises `start_list_capabilities.registration_bindings_versions: [1]`;
a client reports success only after the server acknowledges `registration_bindings_revision`.
Offline files need a versioned sidecar with a digest of the text file it describes.

Costs compared with A: a second representation of the same list to keep consistent, a sidecar that
can be lost or go stale beside its text file, a capability handshake, and nothing for a race whose
start list never reached the site. Its advantage, untouched line layout, matters less once the
existing readers are known to ignore an extra trailing field.

## Rules for either variant

- Do not repurpose comments or change the meaning of fields 0-9; `competitor_id` stays the bib.
- Use `trim-nfc-exact-v1` bib normalization from the photo-index contract.
- Never bind by name. Name/birth-year similarity may only suggest a candidate to a manager.
- Mixed-version tests prove that old SPM, FPG and site responses keep their meaning.

## Historical backfill

Import retained SPM data first; use start/results number rows when no linked SPM record survives.
Stage row source, file digest, event, bib and candidate existing registration; show the original
facts and conflicts to an authorized manager. Name/birth/category similarity suggests a candidate
but never commits identity automatically. One confirmation can apply an unambiguous reviewed batch;
ambiguous or absent entries remain unresolved. Do not require old athletes to re-register.

Personal photos need a confirmed athlete of the registration (see [data model](../data-model.md));
a registration ID alone says which entry got the bib, not who the athlete is. Keep history,
reviewer and corrections. Historical proposals cannot replace a newer SPM-confirmed assignment
without explicit manager resolution. Expose source/status in manager UI.
