# SW_MUSH — Force-Resonant Wilderness Landmarks · Design v1

**Date:** April 26, 2026
**Author:** Opus parallel-track session (CW continuation, fifth half)
**Status:** Content shipped in this drop
**Drop number:** Anchored against Drop F.5 (Dune Sea wilderness) and
  Coruscant Underworld region buildout
**Pre-reads:**
- `jedi_village_quest_design_v1.md` §3.1 (Track B Force-sign trigger sites)
- `clone_wars_era_design_v3.md` §7 (Coruscant Underworld wilderness landmarks)
- `wilderness_system_design_v1.md` (coordinate-based landmark architecture)

---

## 1. Why this exists

The Drop F.8 Village quest design lists four wilderness landmarks as
Track B Force-sign trigger sites:

> **Track B — accumulation track.** Characters who failed the chargen
> roll can still earn Force-sensitivity through gameplay over weeks.
> Trigger conditions (any of):
>   - Combat resolution — you take damage but survive a round you
>     "shouldn't have" (low-probability dodge success, narratively).
>   - **Entering a wilderness room flagged `force_resonant: true`** (e.g.
>     `forgotten_jedi_shrine` in Coruscant Underworld, Bantha Graveyard
>     on Tatooine, several Dune Sea coordinate tiles).
>   - Sleeping/resting in a player home or cantina.

The four landmarks named — `forgotten_jedi_shrine`,
`dune_sea_anchor_stones`, `dune_sea_ruined_obelisk`, `bantha_graveyard`
— were designed but not authored. None of them existed anywhere in the
repo as of the v4 drop. They were references with nothing to reference.

This drop authors them. Pure content; the wilderness builders pick
them up when those drops ship.

---

## 2. What ships

### 2.1 `data/worlds/clone_wars/wilderness/force_resonant_landmarks.yaml` (NEW)

Four wilderness landmark records:

| Landmark | Region | Coords | Resonance flavor |
|---|---|---|---|
| `forgotten_jedi_shrine` | Coruscant Underworld | (12, 38), low level | Sacred but unremembered; a Jedi presence preserved by no one |
| `dune_sea_anchor_stones` | Tatooine Dune Sea | (38, 18) | Pre-Republic; tribal avoidance; older than the Tusken cycle |
| `dune_sea_ruined_obelisk` | Tatooine Dune Sea | (29, 24) | Deliberately defaced; someone wanted it forgotten more than they wanted it standing |
| `bantha_graveyard` | Tatooine Jundland | (16, 31) | Living-world resonance; Tusken sacred care; the Force in tended death |

Each landmark has:
- Hand-authored description (~6-8 lines of fiction-grade prose)
- `properties.force_resonant: true` (the engine flag for Track B)
- `properties.wilderness_landmark: true`
- `properties.director_managed: false` (these rooms are *outside* the
  faction-influence model)
- 4-6 ambient lines that surface as flavor on entry/dwell
- `cross_references:` field documenting where the landmark is referenced
  in other YAML files

Two landmarks have special properties beyond the standard set:

- **`dune_sea_anchor_stones`** has `village_quest_anchor: true`. The
  Village quest's Step 2 ("Crossing the Dunes") completion handler
  watches for the room transition from this landmark west into
  `village_outer_watch`. The first-light condition is narrative-only;
  any time accepts the transition mechanically.

- **`bantha_graveyard`** has `weapon_carry_hostile: tusken_attention`.
  The Tuskens treat this site as sacred and entrants who carry weapons
  draw social pressure (a Tusken NPC approaches but does not attack
  unless a weapon is drawn). The Force-resonant ambient lines fire
  regardless of the social outcome.

### 2.2 `verify_force_resonant_landmarks.py` (NEW)

60 schema + cross-reference checks. Validates:
- Top-level shape, schema_version
- Per-landmark required fields, coordinates type, region known
- `properties.force_resonant: true` (the flag is the whole point)
- `properties.wilderness_landmark: true` and `director_managed: false`
- `ambient_lines` non-empty, well-formed
- Cross-reference: every landmark id is referenced by
  `jedi_village.yaml force_sign_seeds[shrine_entry].rooms`, AND every
  room in that list is defined here (bidirectional resolution)
- `dune_sea_anchor_stones.village_quest_anchor == true`
- Landmark id and name uniqueness

---

## 3. Why each landmark has a distinct flavor

The Village discovery mechanic depends on the player accumulating
Force-signs over weeks of play. If every landmark feels the same, the
mechanic becomes mechanical — repetition without resonance.

The four landmarks were authored to four distinct emotional notes:

**`forgotten_jedi_shrine`** — *sacred but unremembered*. A small
alcove in the Coruscant sublevels. A statue once stood here; the
plaque is unreadable; the Public Works database does not list the
site. Someone died here, or visited, and the Force lingered. The
shrine is not maintained. The candle stub at the empty pedestal is
the only sign of any other visitor — and it's three years old.

**`dune_sea_anchor_stones`** — *pre-Republic*. Three pillars carved
with patterns older than Basic. The Tuskens avoid them — there are
old bone fragments at the southernmost stone, but no recent kills.
Whoever built the stones cared enough to set them carefully and then
disappeared. The Force-resonance is impersonal — not a person's
presence preserved, but a place's purpose preserved.

**`dune_sea_ruined_obelisk`** — *deliberately defaced*. A foundation
half-swallowed by sand. Three sides legible; one side defaced by
hand, not by weather. The Republic survey team noted nothing
remarkable. The defacement matters: someone wanted some part of this
place forgotten more than they wanted it standing. The Force-
resonance is about the *erasure* — the remaining presence is what
someone could not erase.

**`bantha_graveyard`** — *living-world resonance*. A wide depression
where banthas come to die. The Tuskens tend the bones, leave woven
cloth bundles at certain skulls. This is the only landmark of the
four where the Force resonance is bound up with current sacred
practice rather than ancient absence. The candidate hears, faintly,
singing. The bones are warm.

These notes are deliberate. A player visiting all four landmarks over
months should feel that the Force shows up in different shapes — not
just as a "tingle in the air" copy-pasted across every room.

---

## 4. Cross-references resolved

The drop's primary cross-reference is **bidirectional** with the
Village quest YAML:

- **From `jedi_village.yaml` to this file:** The Village quest's
  `force_sign_seeds[shrine_entry].rooms` list names all four
  landmarks. The validator confirms every name resolves to a defined
  landmark in this file.

- **From this file to `jedi_village.yaml`:** Each landmark's
  `cross_references:` field documents where the landmark is
  referenced. The Anchor Stones reference Village quest §3.2 (the
  invitation) and the quest YAML's `starting_room` field. The shrine
  references §3.3 lore foreshadowing.

The validator enforces this bidirectionally — orphan landmarks (defined
here but not referenced) and unresolved references (in Village but not
defined here) both fail.

---

## 5. What this enables

### 5.1 The Village discovery mechanic now has substance

Before this drop, the Village quest design said "a player who explores
wilderness landmarks will accumulate Force-signs over time" — but
those landmarks didn't exist. A player exploring the wilderness would
hit empty pins on the map.

After this drop, the four named landmarks have:
- Atmospheric descriptions that establish *why* the Force resonates
  here (in fiction)
- Ambient lines that surface that resonance in moment-to-moment play
- The `force_resonant: true` flag the engine checks for Track B
  trigger probability

The Village quest's discovery mechanic is now content-substantiated,
not just content-named.

### 5.2 The wilderness region builders have authored content to lift

When Drop F.5 (Dune Sea wilderness) and the Coruscant Underworld
region buildout ship their builders, they read this file directly:

```python
def build_wilderness_landmarks(region: str):
    data = yaml.safe_load(open(
        f"data/worlds/clone_wars/wilderness/force_resonant_landmarks.yaml"
    ))
    for landmark in data["landmarks"]:
        if landmark["region"] == region:
            create_room(
                slug=landmark["id"],
                name=landmark["name"],
                description=landmark["description"],
                short_desc=landmark["short_desc"],
                properties=landmark["properties"],
                ambient_lines=[l["text"] for l in landmark["ambient_lines"]],
                wilderness_coordinates=landmark["coordinates"],
            )
```

No additional authoring required.

### 5.3 The Anchor Stones → Village navigation is wired

The Village quest's Step 2 "Crossing the Dunes" requires the player
to walk WEST from the Anchor Stones at first light. The Anchor Stones
landmark now has `village_quest_anchor: true` set, so the engine
knows to check for the `village_outer_watch` transition from this
specific room.

---

## 6. What this drop does NOT do

- **Does not build the rooms.** The `wilderness/` builder is not in
  this drop; the file is content the builder will read.
- **Does not author other wilderness landmarks.** Coruscant Underworld
  has 5 named landmarks per `clone_wars_era_design_v3.md` §7.3
  (`black_sun_crawler_hideout`, `forgotten_jedi_shrine`,
  `abandoned_factory_dominus`, `uscru_entertainment_district_fringe`,
  `maze_the_reaper_territory`). This drop authors only
  `forgotten_jedi_shrine` because it is the only one of the five that
  is `force_resonant`. The other four are not Village-quest-relevant
  and belong to a separate Coruscant Underworld content drop.
- **Does not author the Mos Eisley old-Jedi rumor NPC.** Per Village
  design §3.3, "A drunken Twi'lek in Chalmun's Cantina has a 3% chance
  per visit of muttering about 'the old hermit in the deep dunes who
  knows things he shouldn't.'" That's an NPC dialogue branch, not a
  room — belongs to a Mos Eisley NPC dialogue authoring pass.
- **Does not author the Coruscant Jedi Archives research mission.** Per
  Village design §3.3, a research mission in the Archives mentions a
  "lost lineage" that left the Order. That's a Republic-faction-gated
  mission — belongs to a Republic Jedi-faction content drop.
- **Does not modify chargen, era.yaml, or anything engine-side.** The
  config knob `force_sign_probability_per_trigger` (default 0.03) goes
  in era.yaml during the F.8 engine session, not here.

---

## 7. Sign-off

The four Force-resonant landmarks are now content-substantiated. The
Village quest's Track B accumulation mechanic has rooms that exist,
descriptions that establish why they resonate, and ambient lines that
surface the resonance in play. The validator confirms bidirectional
cross-reference with `jedi_village.yaml`.

The wilderness region builders (Drop F.5 for Dune Sea; Coruscant
Underworld's existing/future builder) read this file directly when
they ship — no additional authoring required.

*— Opus, parallel CW track, April 26 2026 (continuation pt 5)*
