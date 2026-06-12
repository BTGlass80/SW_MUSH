# SW_MUSH — Coruscant Underworld Non-Resonant Landmarks · Design v1

**Date:** April 26, 2026
**Author:** Opus parallel-track session (CW continuation, sixth half)
**Status:** Content shipped in this drop
**Drop number:** Anchored against `clone_wars_era_design_v3.md` §7
**Pre-reads:**
- `clone_wars_era_design_v3.md` §7 (Coruscant Underworld Wilderness Launch Region)
- `force_resonant_landmarks_design_v1.md` (this drop's predecessor — `forgotten_jedi_shrine`)
- `wilderness_system_design_v1.md` (coordinate-grid wilderness architecture)

---

## 1. Why this exists

`clone_wars_era_design_v3.md` §7.2 names FIVE anchored landmarks in
the Coruscant Underworld wilderness region:

| Landmark | Coords | Level | Role |
|---|---|---|---|
| `black_sun_crawler_hideout` | (20, 15) | mid | Bounty-hunter mission anchor |
| `forgotten_jedi_shrine` | (12, 38) | low | Jedi Village Act 1 foreshadow |
| `abandoned_factory_dominus` | (30, 5) | low | Smuggler contraband cache |
| `uscru_entertainment_district_fringe` | (8, 20) | mid | NPC cluster, jobs hub |
| `maze_the_reaper_territory` | (25, 25) | bottom | High-danger hostile NPC zone |

Plus three transit nodes (`transit_shaft_alpha`, `transit_shaft_beta`,
`surface_manhole_to_southern_underground`) that connect the levels and
the city.

The previous drop (Force-resonant wilderness landmarks) authored
`forgotten_jedi_shrine` because it's the only Force-resonant one and
fit cleanly with the Tatooine landmarks the Village quest depends on.

This drop authors the remaining FOUR landmarks plus the THREE transit
nodes. With both files in place, the Coruscant Underworld region's
anchor set is content-complete.

---

## 2. What ships

### 2.1 `data/worlds/clone_wars/wilderness/coruscant_underworld_landmarks.yaml` (NEW)

Four landmark records and three transit-node records.

**Landmarks** (each with hand-authored description, ambient lines,
typed properties, and `cross_references:` documentation):

- **Black Sun Crawler Hideout** — A converted city-maintenance crawler
  reinforced as a Black Sun operations point. The Sun sigil is fresh
  paint over older Sun paint — territory has changed hands. Two
  visible lookouts, a third on perimeter patrol. BHG miniboss content.
  `faction_anchor: black_sun`, `hostile_default: true`,
  `threat_tier: miniboss`.

- **Abandoned Factory Dominus** — A Republic-era munitions plant
  shuttered fifteen years ago in a Senate corruption inquiry. Upper
  floors structurally compromised; lower assembly bays intact and
  used by smugglers. The half-finished blast rifles on the conveyor
  are the strongest atmosphere note. `gameplay_role:
  smuggler_contraband_cache`, `structural_hazard: true`.

- **Uscru Entertainment District Fringe** — The frayed edge of the
  Uscru entertainment district, two levels below Outlander Club /
  Galaxies Opera. Cantinas that don't ask questions, secondhand gear
  shops, a literal cracked plaster wall serving as the jobs board.
  The Director-managed NPC cluster. `npc_cluster: true`,
  `job_board: true`, `director_managed: true`.

- **The Reaper's Maze** — Bottom-level folklore-tier deterrent zone.
  Whether the Reaper is a creature, a gang, or a rumor depends on
  who you ask. Architecture loops in patterns that should not be
  possible. `cartography_unstable: true` (engine may permute exit
  destinations between visits), `threat_tier: lethal`,
  `low_level_warning: true`.

**Transit nodes** (utilitarian, ambient-disabled, no NPCs):

- **Transit Shaft Alpha** — Mid ↔ Low cargo lift, rusted but functional
- **Transit Shaft Beta** — Low ↔ Bottom service ladder. `requires_climb_check: true`
- **Surface Manhole to Southern Underground** — The single explicit
  city ↔ wilderness handoff per design §2.3.1. Wires to the
  `coruscant_lower` zone's `southern_underground` room via a named
  `manhole` exit on the city side.

### 2.2 `verify_coruscant_underworld_landmarks.py` (NEW)

102 schema + cross-reference checks. Validates:

- Top-level shape (4 landmarks + 3 transit nodes exact)
- Canonical landmark IDs match design §7.2 exactly
- Coordinates and levels match design §7.2 exactly (regression-safe
  against future design drift)
- Per-landmark schema (id, name, region, coords, level, descs,
  properties, ambient_lines)
- Region == `coruscant_underworld` for every record
- None of the 4 non-resonant landmarks have `force_resonant: true`
  (negative assertion — this is the differentiator from the predecessor file)
- Per-landmark special properties (uscru: Director-managed, npc_cluster,
  job_board; maze: cartography_unstable, threat_tier lethal,
  low_level_warning; factory: structural_hazard; black_sun: hostile,
  miniboss tier, faction_anchor)
- Transit nodes have `transit_node: true`, `wilderness_landmark: false`,
  `ambient_disabled: true`, valid `connects_levels` lists
- Surface manhole has `city_handoff: true` and references
  `coruscant_lower` zone + `southern_underground` room
- Transit shaft beta has `requires_climb_check: true`
- **Cross-file check** with `force_resonant_landmarks.yaml`: combined
  set of region-`coruscant_underworld` landmarks across both files
  exactly equals the design §7.2 anchor set (no missing, no extras,
  `forgotten_jedi_shrine` only in the resonant file)
- ID uniqueness across landmarks + transit_nodes

---

## 3. Why each landmark has a distinct atmosphere

Like the Force-resonant landmarks before, each non-resonant landmark
was authored to a distinct atmospheric register so visiting them
across a play session doesn't feel like copy-paste:

**Black Sun Crawler Hideout** — *open menace*. The Sun does not hide;
the lookouts watch you openly; the comms answer in Huttese. The fact
that the sigil is fresh paint over older sigils tells you this place
has changed hands more than once, recently. The atmosphere is "they
will fight you if you push."

**Abandoned Factory Dominus** — *frozen abandonment plus active
absence*. The half-finished blast rifles on the conveyor are the
diegetic anchor: this place stopped suddenly fifteen years ago and
has been almost-but-not-quite empty since. The smugglers don't live
here; they pass through. The footprints don't trace toward the upper
floors because the upper floors are unsafe — but smugglers know that
and only the ignorant go up. The atmosphere is "this place was
killed but won't lie down."

**Uscru Entertainment District Fringe** — *displaced glamour*. Neon
from above flickers in chromatic patches; the song from the unseen
Sullustan singer is a war ballad with the verses changed; the spray-
painted "THE WAR PAYS BETTER UP THERE" sums up the demographic. This
is where people who want to be in Uscru proper but can't afford it
go to feel like they're in Uscru. The atmosphere is "the city's
hangover one level down."

**The Reaper's Maze** — *folklore-tier hostile*. The atmosphere is
the most aggressive of the four because the gameplay role is
deterrent. The bones with bite-radius unmatched to any species, the
red-air lighting with no fixture, the absent rats — all designed to
make a low-level character feel that they have walked into someplace
that is not for them. The cartography_unstable property is mechanical
encoding of the "the corridor behind you is gone" effect — players
who survive a Maze visit should describe paths that did not exist
when they entered.

The transit nodes are deliberately *atmosphere-free*. They are
infrastructure. Their `ambient_disabled: true` flag tells the engine
to skip ambient pool surfacing — players moving through a transit
node should feel like they are in transit, not in a place.

---

## 4. The Surface Manhole — the one explicit handoff

`clone_wars_era_design_v3.md` §2.3.1 specifies:

> **Underworld connection:** the Southern Underground zone has one
> explicit exit downward (a named exit, `manhole` or `vent`) into the
> Coruscant Underworld wilderness region. That's the gateway to the
> coordinate-based wilderness tiles — a single clear handoff point.

This drop encodes the wilderness-side of that handoff:

```yaml
- id: surface_manhole_to_southern_underground
  connects_to_zone: coruscant_lower
  connects_to_room: southern_underground
  properties:
    city_handoff: true
```

The city-side complement (a named exit `manhole` from
`southern_underground` pointing to this transit node) lives in
`data/worlds/clone_wars/planets/coruscant.yaml` and is NOT touched by
this drop. When the wilderness builder ships, it validates the
round-trip: the manhole's `connects_to_room` must declare an exit
back to this transit node, and the city-side exit must declare its
target as `surface_manhole_to_southern_underground`. Either side
missing fails the load.

The named exit on the city side is currently absent — `coruscant.yaml`
v34 has the southern_underground room but no `manhole` exit yet. That
exit gets added when the wilderness builder lands; it's a small
city-side edit, out of scope for this content drop.

---

## 5. Cross-references — the bidirectional check

The validator does a **cross-file** check against
`force_resonant_landmarks.yaml`:

```python
combined = resonant_underworld_ids ∪ nonresonant_ids
expected = {forgotten_jedi_shrine, black_sun_crawler_hideout,
            abandoned_factory_dominus, uscru_entertainment_district_fringe,
            maze_the_reaper_territory}
assert combined == expected
```

This catches:
- A landmark appearing in both files (engine ambiguity)
- A landmark missing from both files (incomplete coverage)
- A landmark in the wrong file (e.g. `forgotten_jedi_shrine`
  accidentally non-resonant)
- A rogue landmark in either file (typo, scope creep)

The check passes only if the two files together exactly cover the
design §7.2 landmark set. This is the regression-test asset for the
Coruscant Underworld wilderness builder.

---

## 6. What this enables

### 6.1 Coruscant Underworld wilderness region is content-complete

Before this drop:
- `forgotten_jedi_shrine` authored (Force-resonant landmarks file)
- 4 other landmarks named in design but no descriptions, ambient lines,
  or properties
- 3 transit nodes named in design but unauthored

After this drop:
- All 5 landmarks fully authored across the two files
- All 3 transit nodes authored
- Bidirectional validator confirms exact coverage

The Coruscant Underworld wilderness builder, when it ships, reads
both files filtered by `region: coruscant_underworld` and creates
all 8 anchor records (5 landmarks + 3 transit nodes) without any
further authoring.

### 6.2 BHG miniboss content has a target

The Bounty Hunter tutorial chain (`chains.yaml`) graduates the player
to "pull contracts from the Guild board." The Black Sun Crawler
Hideout is now the canonical mid-game miniboss target — the
Adjudicator at the Nar Shaddaa BHG chapter house can flag contracts
naming Black Sun lieutenants, with the hideout as the location.

### 6.3 Smuggler chain has a contraband cache

The Smuggler tutorial chain teaches the cargo system. Abandoned
Factory Dominus is now the canonical lower-level Coruscant cargo
drop site for smuggler missions originating in the Hutt Cartel /
independent network.

### 6.4 The jobs hub has an address

`uscru_entertainment_district_fringe` is the canonical mid-game
non-Republic jobs hub on Coruscant. Players running independent /
underworld content past the tutorial pull from this site as much as
from the Mos Eisley spaceport. The Director-managed NPC cluster gives
it the lived-in feel of a real city plaza, not a quest pin.

### 6.5 The Maze is a real deterrent

`threat_tier: lethal` plus `low_level_warning: true` plus
`cartography_unstable: true` together encode a zone that punishes
low-level characters mechanically and atmospherically. The engine
session can wire the warning prompt when a character below threshold
attempts to enter, and the cartography permutation when they're
inside — both backed by the design and the authored content.

---

## 7. What this drop does NOT do

- **Does not build the wilderness region.** The Coruscant Underworld
  builder is engine work; this drop is content the builder consumes.
- **Does not add the city-side `manhole` exit** to
  `coruscant.yaml`'s `southern_underground` room. That's a small
  city-side edit, scoped to the wilderness-builder drop.
- **Does not author the Black Sun lieutenant NPCs** that are the
  miniboss content. The Black Sun crawler is the location; the NPCs
  are a separate roster pass.
- **Does not author the Reaper's Maze hostiles.** Same reason —
  the Maze is the location with the cartography mechanic; the
  creatures or gang inside are a separate spawn-list pass.
- **Does not encode the cartography permutation logic.** The
  `cartography_unstable: true` flag is the engine signal; the
  permutation algorithm is engine-side.
- **Does not author the rakghoul-descendant lore.** The Maze
  description hints at "a Coruscant rakghoul descendant or worse" as
  one folklore explanation for the Reaper, but the actual species
  detail (if any) is deferred.

---

## 8. Sign-off

The Coruscant Underworld wilderness region's anchor set is now
content-complete across two files: `force_resonant_landmarks.yaml`
(forgotten_jedi_shrine plus 3 Tatooine landmarks) and this drop's
`coruscant_underworld_landmarks.yaml` (4 non-resonant Coruscant
landmarks plus 3 transit nodes).

102 schema + cross-reference checks pass at authoring time. The
bidirectional cross-file check confirms exact coverage of design
§7.2's 5-landmark set. The wilderness builder can read both files
when it ships and create all 8 anchor records (5 landmarks + 3
transit nodes) with their authored descriptions, ambient pools, and
typed properties.

The content surface for the launch wilderness region is now closed.
Engine work for Drop F.5 (the wilderness region itself) consumes
this content directly; no further authoring is required for any
mechanically-gated region content.

*— Opus, parallel CW track, April 26 2026 (continuation pt 6)*
