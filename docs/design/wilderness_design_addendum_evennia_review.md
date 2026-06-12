# Wilderness Design Addendum — Evennia Review

**Date:** May 3, 2026
**Context:** Pre-Drop W.2 phase 2 design pause. Brian reviewed Evennia's
`evennia.contrib.grid.wilderness` (the original inspiration) and asked
whether our implementation is missing anything interesting.
**Companion to:** `wilderness_system_design_v1.md`
**Supersedes:** sections of W.2 phase 2 scope (no major reversals — this
adds rather than replaces).

---

## Summary

Evennia confirms our design intuition but reveals **three things worth
adopting** before W.2 phase 2 lands the live command surface. The most
important is **co-location semantics** — without it, two PCs at the
same wilderness coordinates would be invisible to each other, which
breaks the "wilderness is real space" property.

## How Evennia does it (short version)

Evennia's wilderness is a **single Script** (their persistent runtime
object) that owns:

- A dict mapping `object → (x, y)` coordinates
- A pool of **real Room objects**, recycled across coordinates
- An `unused_rooms` storage list

When a player moves, Evennia:
1. Looks up (or creates, or recycles from `unused_rooms`) a Room object
   for the destination coordinates
2. Sets the Room's `ndb.active_coordinates` and `ndb.active_desc`
3. Moves the player object to that Room
4. **If two players end up at the same coordinates, they end up in the
   same Room object** — sharing the room is automatic
5. When a player leaves a coordinate, if no other players are there,
   the Room gets returned to `unused_rooms`

The cleverness: rooms aren't created per coordinate, they're created
per occupied coordinate. A region with 1,600 tiles and 5 active players
spread out has 5 active rooms, plus some unused ones in the pool.

## Why we differ

Our stack doesn't need this trick:
- We're on async SQLite + custom command handlers, not Django ORM with
  required-object exits.
- Our movement system can compute tile descriptions from a pure
  function and persist coordinates as columns on `characters`.
- We have ONE sentinel room per region; the player's "actual location"
  is `(wilderness_region_slug, x, y)` on the character.

This is **simpler in most respects**: trivially durable across
restarts, no recycling logic, no per-coordinate ndb juggling. But it
has one consequence Evennia gets for free that we DON'T:

> When two PCs are at the same wilderness coordinates in our model,
> they share the sentinel `room_id`, but so does *every* PC anywhere
> in the region. Standard "who's in this room" logic would either
> show too many people (everyone in the region) or nobody (if filtered
> incorrectly).

This is the gap that needs closing before W.2 phase 2 ships
`MoveCommand` integration. Otherwise it'll be wired against broken
co-location and have to be revisited.

---

## The three changes we should make

### 1. Co-location semantics (REQUIRED before W.2 phase 2)

**The rule:** two PCs are "in the same place" when one of these holds:
- Both are in a normal room (same `room_id`, both have NULL wilderness state)
- Both are in the same wilderness tile (same `wilderness_region_slug`,
  same `wilderness_x`, same `wilderness_y`)

**Where this affects code:**

| Surface | Current logic | What it should do |
|---|---|---|
| `look` room contents | List all characters with `room_id = self.room_id` | If self is in wilderness, list characters with same `(slug, x, y)`. Else current logic. |
| `say` / `whisper` broadcast | Send to all sessions in `room_id` | If source is in wilderness, send to sessions whose character has same `(slug, x, y)`. |
| `_broadcast_arrival` / `_broadcast_departure` | Broadcast to all in old/new `room_id` | Wilderness path: broadcast to characters with matching wilderness coords (per source's pre/post coords), NOT all sentinel-residents. |
| `look <playername>` (looking AT another PC) | Find by name in same `room_id` | If self in wilderness, restrict to same `(slug, x, y)`. |

**Implementation approach:** introduce a single helper function
`engine.wilderness_movement.same_location(char_a, char_b) -> bool`
that callers can use uniformly. Plus a query helper
`engine.wilderness_movement.characters_at_tile(db, slug, x, y) -> list`
that the broadcast surfaces consume.

The DB index we already added (`idx_characters_wilderness_region` on
`wilderness_region_slug`) is enough for the query to be efficient at
launch scale; if it gets hot, we can index `(slug, x, y)` later.

This is a 1–2 day implementation effort — touches a handful of well-
defined call sites and is testable in isolation.

### 2. `is_valid_coordinates` callback (NICE TO HAVE)

Evennia's per-coordinate validity check lets non-rectangular regions
exist (the pyramid example) and blocks specific tiles inside the
rectangle (cliff faces, exclusion zones).

We get rectangular bounds for free from `region.grid_width/height`.
What we don't get is **per-tile blocking** — useful for things like
"this tile is the inside of a sandstone column, not walkable" or
"military no-fly zone."

**Proposed shape:** add an optional `unwalkable_tiles:` list to the
region YAML:

```yaml
unwalkable_tiles:
  - coords: [15, 22]
    reason: "A vertical sandstone column blocks the way."
  - region_block:
      x1: 30
      y1: 30
      x2: 32
      y2: 32
    reason: "The earth here is glassed and hot."
```

Mirrors the existing `tile_assignments:` block format. Loader stores
as a `WildernessRegion.unwalkable: dict[tuple, str]`. The kernel's
`move_in_wilderness` consults it after bounds check; on a hit, returns
`MoveResult(ok=False, reason=<reason>)`.

**Scope decision:** Drop 2 phase 2 adds the loader hook + kernel
consultation, but the Dune Sea YAML doesn't use any unwalkable tiles
yet. Empty dict is the default. So it ships as an inert feature for
W.2 phase 2 and gets exercised when a future region needs it.

### 3. Pool concept naming (DOCUMENTATION ONLY)

Evennia's `WildernessMapProvider` is a clean abstraction: "the thing
that knows the shape of the map." We have this implicitly — the
YAML+loader IS our map provider — but naming it explicitly in the
design doc clarifies the architecture for future authors:

> A region YAML + the loader's parsing logic together constitute a
> "map provider." Future regions are added by writing a new YAML, not
> by writing new Python. This is a deliberate architectural choice:
> content authors don't need to subclass anything.

**Scope:** documentation-only. No code change.

---

## What we are NOT adopting from Evennia

A few things looked clever but don't fit our stack:

### Room recycling pool (`unused_rooms`)

Solves a Django-ORM problem we don't have. Our sentinel + character-
coord-columns model means we never create per-coordinate rooms, so
there's nothing to recycle.

### Object-merging into shared rooms

Evennia merges PCs into the same room object when they share coords.
We could simulate this by checking the (slug, x, y) tuple on every
look/say/etc., but the simulation is the actual solution — we don't
need rooms to be "the same object," we just need our co-location query
to treat them as such (item #1 above).

### `at_prepare_room` Python hook

Evennia provides a Python hook on the room class for runtime
description tweaking. Our `render_tile()` already does this via the
YAML's `variants:` and `time_overlays:` — declarative. If we ever need
runtime-computed descriptions (e.g., "this tile is currently on fire
because an encounter is active"), we can add a `dynamic_overlays`
parameter to `render_tile` without restructuring.

### Map provider as Python class

Evennia subclasses `WildernessMapProvider` for each region. That's a
viable extensibility model but it's heavier than YAML. We chose YAML
because content-only changes shouldn't require Python edits. If a
region ever needs Python-level extensibility, we can introduce a hook
file alongside the YAML at that time.

---

## Updated Drop W.2 phase 2 scope

Original scope (pre-pause):

> Live `MoveCommand` integration, `LookCommand` integration, edge
> crossings between hand-built rooms and wilderness, edge YAML format,
> `coords` command.

Updated scope (post-Evennia review):

> Same as above, **plus**:
>
> 1. `engine.wilderness_movement.same_location()` and
>    `characters_at_tile()` helpers.
> 2. Co-location consultation in `look_room_contents`, `say`, `whisper`,
>    `_broadcast_arrival`, `_broadcast_departure`. Wilderness branch
>    only — normal-room path unchanged.
> 3. Loader support for `unwalkable_tiles:` (inert until exercised).
> 4. Kernel consultation of unwalkable tiles in `move_in_wilderness`.
>
> No change to: edge format (still `room_slug + coords +
> direction_from_room + direction_back_to_room`), look rendering, the
> `coords` command, schema.

Estimated effort delta: +0.5 to +1 session. Worth it because rewiring
co-location after the live commands ship is a much bigger change.

---

## Test additions (preview)

For the co-location work specifically:

| Test | Purpose |
|---|---|
| `same_location` truth table | Both NULL, both same room, both same tile, mismatched | one wilderness one normal | mismatched coords |
| `characters_at_tile` returns only same-tile PCs | Three PCs in same region, different tiles, query returns one |
| `look` from wilderness shows only same-tile players | Two PCs in Dune Sea at different coords don't see each other |
| `look` from wilderness shows other PC at same tile | Two PCs at (12, 18) DO see each other |
| `say` in wilderness reaches only same-tile players | Mixed positions, source at (12, 18); only matching recipients receive |

These slot into `test_wilderness_drop2_phase2.py` (new file) alongside
the live-command tests.

---

## What this means for sequencing

W.2 phase 2 grows from "wire the kernel into commands" to "wire the
kernel into commands AND fix co-location." Realistically:

- W.2 phase 2 (this iteration): co-location helpers + edge format +
  `MoveCommand` wilderness branch + `LookCommand` wilderness branch +
  unwalkable tiles loader hook. Tests.
- W.2 phase 3 (next): `say`/`whisper`/broadcast surfaces consult
  co-location helpers. `coords` command. Tests.
- W.2 phase 4 (next next): movement edge cases, error message polish,
  any UX refinements.

Splitting at "movement works but says/whispers don't yet" is honest
and incremental. Each phase ships a felt feature.

---

## Recommendation

**Proceed with Drop W.2 phase 2 as scoped above** — the co-location
helpers and unwalkable-tiles hook are small additions that prevent a
bigger refactor downstream, and the Evennia review surfaced exactly
the kind of "missing thing" Brian asked about.

We don't need to rewrite the kernel or the schema. The W.2 phase 1
foundation holds up against Evennia's design choices; the additions
are deltas on top of it, not replacements.

The architectural difference from Evennia (sentinel + coord columns
vs. recycled real rooms) is correct for our stack. We pay for it with
having to add explicit co-location queries instead of getting them
"free" from object identity. That cost is small and well-bounded.

---

*If Brian agrees with this addendum, we proceed with W.2 phase 2 in
the updated scope. If he wants to defer co-location to phase 3 and
ship a smaller phase 2, that's also valid — but the live commands will
need a re-touch when phase 3 lands.*
