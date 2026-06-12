# World Data Extraction — Design Document v1

**SW_MUSH · April 18, 2026 · Prerequisite refactor for Wilderness system and future era swaps**

---

## 1. Problem Statement

`build_mos_eisley.py` is ~2,369 lines of Python that hardcodes every room, exit, NPC, housing lot, and zone in the four-planet GCW world. It's the last major system in the codebase that violates the project's established **"world content is data, not code"** principle — every other content domain (skills, species, factions, schematics, achievements, zones, vendor droids, organizations) lives in YAML under `data/` and is loaded at boot.

The build script's structure is three parallel Python literals:

```python
ROOMS = [
    # (id, name, description, zone, planet, map_x, map_y, ...),
    ...
]

EXITS = [
    # (from_id, to_id, forward_direction, reverse_direction),
    ...
]

PLANET_NPCS = [
    # NPC dicts keyed on room_id,
    ...
]
```

Plus ad-hoc code for housing lots, test characters, security zone assignments, and schema migrations folded in.

**Consequences we are paying today:**

1. Wilderness, Clone Wars, and any future world expansion would be written as parallel hardcoded scripts that drift from each other.
2. Adding a room requires editing Python, which means full-file rewrites through the session workflow.
3. The tutorial bugfix history shows exit-collision bugs that are a direct consequence of the tuple format — easy to mis-edit, hard to validate statically.
4. 120 rooms with hand-tuned `map_x`/`map_y` coordinates are embedded in tuple position 5 and 6, invisible in diffs and untestable except by running the build.
5. Room indices are position-dependent — shifting the list reshuffles the whole world, which is why every world-builder version requires a full DB wipe.

**The refactor's single job:** extract all world content to YAML under `data/worlds/<era>/`, keep GCW as the only era, produce a byte-equivalent database. No feature change, no user-visible change. Foundation-only.

---

## 2. Design Goals

**Primary (must have):**

1. **Round-trip equivalence.** A fresh DB built from YAML is functionally equivalent to one built from the current Python script. Same rooms, same exits, same NPCs, same zone assignments, same housing lots, same map coordinates.
2. **Era-parameterized loader.** A single `load_world.py` reads `data/worlds/<active_era>/` based on a config setting. GCW is the only era shipped in this refactor.
3. **Stable room IDs.** World builds produce deterministic, stable integer IDs so existing test scripts, design docs, and quest data referencing specific room IDs (e.g., "Docking Bay 94 = room 0") continue to work.
4. **Validated on load.** Malformed YAML, duplicate room slugs, exit references to nonexistent rooms, and direction collisions all fail loudly at boot with actionable error messages, not silently at runtime.

**Secondary (should have):**

5. **Human-editable.** A builder can add a room by editing one YAML file, not navigating a 2,369-line Python tuple-fest.
6. **Diffable.** Changes show up as one-line diffs in version control, not large blocks of shifted Python.
7. **Partial loads.** A single planet's content lives in its own file; you can edit Tatooine without opening Corellia.

**Non-goals (explicit):**

- **Not** a runtime era switcher. Era is a boot-time config. Switching eras requires a DB rebuild.
- **Not** a web-based room editor. That's a future project.
- **Not** generic MUSH softcode. Content is declarative YAML; logic stays in Python.
- **Not** a migration away from the existing `rooms`/`exits` DB schema. We're changing where content comes from, not where it lives.
- **Not** a change to how rooms are used at runtime. The loaded DB is identical in structure to today's.

---

## 3. Target Directory Layout

```
data/
├── worlds/
│   ├── gcw/                                    # Galactic Civil War (current content)
│   │   ├── era.yaml                            # Era metadata + policy knobs
│   │   ├── zones.yaml                          # 20 zones with security tiers
│   │   ├── planets/
│   │   │   ├── tatooine.yaml                   # 54 rooms + exits
│   │   │   ├── nar_shaddaa.yaml                # 30 rooms + exits
│   │   │   ├── kessel.yaml                     # 12 rooms + exits
│   │   │   └── corellia.yaml                   # 24 rooms + exits
│   │   ├── npcs.yaml                           # All planet NPCs (39 entries)
│   │   ├── housing_lots.yaml                   # Tier 1-5 lots (rented rooms, shopfront lots, HQ lots)
│   │   └── test_character.yaml                 # Test user / god-mode account definition
│   │
│   └── clone_wars/                             # Future — not built in this refactor
│       └── (parallel structure)
│
└── (existing data/ files untouched: skills, species, schematics, factions, etc.)
```

**Why split by planet:** Tatooine is the biggest and most-edited chunk. Keeping it in one file per planet means editing a room in Mos Eisley doesn't conflict-diff against Corellia work. Zones and NPCs are cross-planet and stay in flat files.

**Why `era.yaml` at the top:** It's the per-era configuration object — active timeline name, starting date, any era-specific policy knobs (Force chargen rules, default faction set, etc.). Even if we don't need these knobs today, the file exists as the anchor for the era so it's obvious where to add them later.

---

## 4. Schema — YAML Formats

### 4.1 `era.yaml`

```yaml
era:
  code: gcw
  name: "Galactic Civil War"
  description: >
    Set shortly after the Battle of Yavin. The Empire dominates, the Rebel
    Alliance operates in the shadows, and Force-users are rare and hunted.
  timeline_reference: "0 ABY – 4 ABY"

# Policy knobs — consulted by engine at boot, optional fields are optional
policy:
  # Force policy — reserved for future Force-chargen-gating work; currently inert
  force_chargen_allowed: false
  force_sensitive_chargen: true
  lightsaber_availability: rare

  # Default faction set — must match factions.yaml (already keyed by code)
  # If empty, all factions in data/organizations.yaml are active.
  factions: [empire, rebel, hutt, bh_guild, independent]

  # Starting room for new characters
  starting_room_slug: docking_bay_94_entrance

content_refs:
  zones: zones.yaml
  planets:
    - planets/tatooine.yaml
    - planets/nar_shaddaa.yaml
    - planets/kessel.yaml
    - planets/corellia.yaml
  npcs: npcs.yaml
  housing_lots: housing_lots.yaml
  test_character: test_character.yaml
```

The `content_refs` section is the loader's manifest. The loader reads these explicit paths rather than globbing the directory — this makes it obvious what's loaded and in what order.

### 4.2 `zones.yaml`

Zones are the security-tier containers. Current live state: 20 zones across 4 planets.

```yaml
zones:
  - slug: mos_eisley_core
    name: "Mos Eisley core"
    planet: tatooine
    security: secured
    narrative_tone_key: tatooine_mos_eisley   # references data/zones.yaml (existing)
    notes: "Spaceport streets, markets, government"

  - slug: spaceport_district
    name: "Spaceport District"
    planet: tatooine
    security: contested

  - slug: jundland_wastes
    name: "Jundland Wastes"
    planet: tatooine
    security: lawless
    notes: "Tusken Raiders, Krayt Graveyard"

  # ... 17 more zones
```

Security values: `secured | contested | lawless` — matches `engine/security.py::SecurityLevel` exactly.

### 4.3 `planets/tatooine.yaml`

The bulk of the data. Each file contains the rooms and exits for one planet.

```yaml
planet: tatooine
display_name: "Tatooine"

rooms:
  - slug: docking_bay_94_entrance
    name: "Docking Bay 94 — Entrance"
    zone: spaceport_district
    map: { x: 10, y: 20 }
    description: |
      The dusty entrance to Docking Bay 94. A YT-1300 freighter sits within,
      its ramp lowered. Loading droids shuffle crates in the heat.
    properties:
      starting_room: true
      tutorial_waypoint: 1

  - slug: mos_eisley_market
    name: "Mos Eisley Market"
    zone: mos_eisley_core
    map: { x: 12, y: 20 }
    description: |
      Rows of stalls line the dusty street. Jawas, Rodians, and humans
      haggle over scavenged parts and moisture vaporator components.

  # ... 52 more Tatooine rooms

exits:
  - from: docking_bay_94_entrance
    to: mos_eisley_market
    direction: north
    reverse: south
    # Optional fields below are all unset in the common case:
    # locked: false
    # key_item: null
    # hidden: false
    # requires_faction: null
    # display_name: "north to the Market"   # only if different from direction

  - from: mos_eisley_market
    to: chalmuns_cantina_entrance
    direction: west
    reverse: east

  # ... all Tatooine exits
```

**Design choices worth calling out:**

- **Room `slug` is the primary key, not an integer.** Slugs are stable, human-readable, searchable, and survive reordering. The loader assigns integer IDs at build time in a deterministic order (see §5.3). Exits and NPCs reference rooms by slug, never by integer.
- **`map` is a nested object, not two top-level fields.** The 120 hand-tuned coordinates from the current build are preserved verbatim — that tuning work is not thrown away.
- **`description` uses YAML block-scalar (`|`).** Newlines preserved; free from quote-escape hell. Long descriptions read naturally in the file.
- **Exits explicitly state `reverse`.** The current `(from, to, forward, reverse)` tuple model is preserved — this captured real GCW cases like "exit goes north but comes back as 'south to Market'." No automatic reverse-inference; authors specify both. The tutorial bugfix history shows why this matters.
- **Optional exit properties** — `locked`, `hidden`, `requires_faction`, `display_name` — are set when needed and omitted when default. The Rebel safehouse hidden-exit case is one `hidden: true` field.

### 4.4 `npcs.yaml`

NPC placements. The NPC *definitions* (stats, dialogue profiles) already live in `data/npcs_gg7.yaml` and species files — this file is just placement.

```yaml
npcs:
  - slug: old_prospector
    name: "Old Prospector"
    room: outskirts_scavenger_market     # room slug
    template_ref: npcs_gg7.yaml#prospector # (conceptual — see §5.4)
    trainer_skills: [survival, search]
    hostile: false
    faction: independent
    description: |
      A weathered human hunched over a hydrospanner, surrounded by
      broken moisture vaporator parts. He glances up with keen eyes.

  - slug: tusken_raider_warband
    name: "Tusken Raider"
    room: jundland_canyon_floor
    hostile: true
    tier: 2                              # feeds npc_generator
    faction: tusken                      # non-org faction, just a tag
    respawn_seconds: 600

  # ... 37 more NPCs
```

### 4.5 `housing_lots.yaml`

Already structurally data-ish in the current code — this just serializes it.

```yaml
housing_lots:
  # Tier 1 rental locations
  - slug: mos_eisley_hotel_rental_1
    tier: 1
    room: mos_eisley_hotel_lobby
    planet: tatooine
    zone: mos_eisley_core
    max_homes: 5

  - slug: chalmuns_backroom_rental
    tier: 1
    room: chalmuns_cantina_bar
    planet: tatooine
    zone: chalmuns_cantina

  # Tier 3 private residences
  - slug: tatooine_residential_lot_a
    tier: 3
    room: mos_eisley_residential_east
    planet: tatooine
    zone: mos_eisley_core
    max_homes: 2
    allowed_tiers: [3, 4]

  # Tier 5 organization HQ lots
  - slug: imperial_garrison_hq_lot
    tier: 5
    room: imperial_garrison_courtyard
    planet: tatooine
    zone: mos_eisley_core
    allowed_orgs: [empire]

  # ... all 20+ lots
```

### 4.6 `test_character.yaml`

The god-mode test account definition, currently hardcoded in the build script.

```yaml
test_account:
  login: testuser
  password: testpass
  flags: [admin, builder]

test_character:
  name: "Test Jedi"
  species: human
  credits: 100000
  attributes:
    dexterity: 5D
    knowledge: 5D
    mechanical: 5D
    perception: 5D
    strength: 5D
    technical: 5D
  skills:
    blaster: 7D
    dodge: 9D
    piloting: 9D
    persuasion: 9D
    lightsaber: 10D
    # ...
  force:
    control: 8D
    sense: 8D
    alter: 7D
  force_points: 5
  equipment:
    - lightsaber
  inventory:
    - medpac
    - medpac
    - dl44_blaster
    - comlink
    - datapad
  tutorial_state: complete
  starting_room: docking_bay_94_entrance
```

---

## 5. The Loader — `load_world.py`

### 5.1 Entry Point

Replaces `build_mos_eisley.py` conceptually. Lives in the project root. Invoked the same way — before first server boot on a fresh DB.

```python
# load_world.py

async def load_world(db, era: str = None) -> BuildReport:
    """
    Load world content from data/worlds/<era>/ into the database.
    If era is None, read config to determine active era.
    Idempotent when rooms already exist (skips and reports).
    """
    era = era or get_config("active_era", default="gcw")
    era_dir = Path("data/worlds") / era

    manifest = load_era_manifest(era_dir)        # §5.2
    zones = load_zones(era_dir, manifest)
    rooms, room_slug_to_id = load_rooms(era_dir, manifest, zones)  # §5.3
    exits = load_exits(era_dir, manifest, room_slug_to_id)
    npcs = load_npcs(era_dir, manifest, room_slug_to_id)
    lots = load_housing_lots(era_dir, manifest, room_slug_to_id)
    test_char = load_test_character(era_dir, manifest, room_slug_to_id)

    # Validation pass — §5.5
    validate_world(zones, rooms, exits, npcs, lots)

    # DB writes, transactional — §5.6
    async with db.transaction():
        await insert_zones(db, zones)
        await insert_rooms(db, rooms)
        await insert_exits(db, exits)
        await insert_npcs(db, npcs)
        await insert_housing_lots(db, lots)
        await insert_test_character(db, test_char)

    return BuildReport(
        era=era,
        rooms=len(rooms),
        exits=len(exits),
        npcs=len(npcs),
        lots=len(lots),
        warnings=[...],
    )
```

### 5.2 Era Manifest

`era.yaml` is loaded first. `content_refs` is the explicit list of files to load. The loader resolves paths relative to the era directory, checks they exist, and bails with a clear error if any are missing. No directory globbing — no surprises from stray YAML files.

### 5.3 Room ID Assignment — The Stability Problem

This is the trickiest part of the refactor, and getting it wrong breaks every test script and quest chain that references rooms by integer ID.

**Current live state:**

```
Tatooine:    rooms 0-53   (54 rooms)
Nar Shaddaa: rooms 54-83  (30 rooms)
Kessel:      rooms 84-95  (12 rooms)
Corellia:    rooms 96-119 (24 rooms)
```

**The rule we adopt:** ID assignment is a deterministic function of (a) planet file order in `era.yaml`'s `content_refs`, and (b) room order within each planet file. The loader walks planets in manifest order, and within each planet assigns IDs 0, 1, 2… in file order.

**Migration from the current script:** The first YAML generation (§6.1) serializes the current Python `ROOMS` list preserving order, so the resulting IDs match the live DB exactly. Room 0 stays Docking Bay 94 Entrance, room 8 stays Mos Eisley Market, and so on.

**Going forward:** New rooms are *appended* to the end of their planet's file, so new IDs are assigned after the existing range. Never reorder existing rooms in YAML — it would shift IDs and break references. This is the same discipline the current script already requires; the YAML just makes it explicit.

**Secondary defense:** The loader emits a `rooms_manifest.json` beside the DB after each build — a sorted list of `{id, slug, planet}` triples. The next build compares against this manifest and fails loudly if any existing slug would be assigned a different ID. This makes accidental reordering an error at build time, not a silent corruption at runtime.

### 5.4 NPC Template References

NPCs in `npcs.yaml` reference templates by a conceptual `template_ref` field like `npcs_gg7.yaml#prospector`. In v1 of the loader, this is just a string read by existing code in `engine/npc_loader.py` — which already reads `data/npcs_gg7.yaml`. We don't refactor the GG7 loader here; we just give the world-NPC entries a way to declaratively reference templates.

Trainer NPCs, hostile NPCs, and merchant NPCs keep their inline stat fields as they do today. The world loader passes them through unchanged.

### 5.5 Validation

Before any DB write, the loader runs these checks and **fails boot** on any error:

1. **Unique room slugs** across all planets.
2. **Unique zone slugs.**
3. **Every exit's `from` and `to` resolve** to real room slugs.
4. **Every exit's direction is valid** — one of `north, south, east, west, northeast, northwest, southeast, southwest, up, down` plus named custom directions matching `^[a-z][a-z0-9_ ]*$`.
5. **No direction collisions per room.** Per room slug, the set of outgoing directions (forward of `from`-exits plus reverse of `to`-exits) must have no duplicates. This is the check the tutorial bugfix had to run by hand; now it's automatic.
6. **Every NPC's `room` resolves** to a real room slug.
7. **Every housing lot's `room` resolves** to a real room slug.
8. **Every zone referenced by a room exists** in `zones.yaml`.
9. **The `starting_room_slug` in `era.yaml` exists.**

Warnings (non-fatal but logged):

- Rooms with no exits in or out (orphans).
- Zones with no rooms.
- Housing lot `max_homes` exceeds sensible bounds (e.g., >10).

### 5.6 DB Writes

The loader opens a single transaction and inserts all world content in order: zones → rooms → exits → NPCs → housing lots → test character. If any insert fails the whole transaction rolls back and the DB is untouched. This replaces the current script's ad-hoc step-by-step writes.

The DB schema is **unchanged**. We're not migrating tables; we're changing who writes to them.

---

## 6. Migration Plan

This is a refactor, and the acceptance criterion is *no behavioral change*. The migration has three phases.

### 6.1 Phase A — YAML Generation (one-shot extraction tool)

Build a one-time extractor: `scripts/extract_world_to_yaml.py`. It:

1. Imports `build_mos_eisley.py` as a module (reads the `ROOMS`, `EXITS`, `PLANET_NPCS`, housing-lot constants, test-character constants).
2. Generates slugs from room names via a deterministic slugifier (lowercase, replace spaces and punctuation with `_`, collision-suffix `_2`, `_3` if needed).
3. Emits `data/worlds/gcw/era.yaml`, `zones.yaml`, `planets/*.yaml`, `npcs.yaml`, `housing_lots.yaml`, `test_character.yaml`.
4. Writes a `scripts/extraction_slug_map.json` artifact — `room_id → slug` — which is the canonical mapping from old integer IDs to new slugs. Committed to the repo for reference; used nowhere at runtime.

Run once, review diffs, commit YAML. `build_mos_eisley.py` stays in the tree during this phase.

### 6.2 Phase B — Loader + Equivalence Test

1. Implement `load_world.py` and all helpers per §5.
2. Implement `scripts/diff_world_builds.py`:
   - Builds DB A from the legacy `build_mos_eisley.py` path.
   - Builds DB B from `load_world.py` reading the new YAML.
   - Diffs both databases row-by-row on the `rooms`, `exits`, `zones`, `npcs`, `housing_lots` tables.
   - **Pass criterion: zero semantic differences.** (Column ordering, insertion timestamp, and rowid may differ; room contents, exit graph, NPC placements, housing lots must be identical.)
3. Pass the equivalence test before the cutover.

### 6.3 Phase C — Cutover

1. `game_server.py` calls `load_world()` instead of `build_mos_eisley()` on fresh-DB boot.
2. `build_mos_eisley.py` is renamed to `build_mos_eisley_legacy.py` and left in the tree for one release cycle as a fallback.
3. The architecture doc is updated: §4 World Layout references `data/worlds/gcw/` as the source of truth; the loader and YAML schema are documented under a new §22 or similar.
4. The `rooms_manifest.json` is generated and committed.
5. Next release: `build_mos_eisley_legacy.py` is deleted.

### 6.4 Live Data

The refactor changes only the *fresh-build* path. Existing live databases are unaffected — we do not rebuild the live world from YAML. Players' character data, housing, ships, quest progress, narrative memory all stay put. If we ever want to hot-reload world content into a live DB, that's a separate project with its own risk calculus.

---

## 7. Impact on Existing Systems

### 7.1 Low-impact / No-change

Everything that reads rooms via `db.get_room()`, `db.get_exits_from()`, `db.get_characters_in_room()`, etc., is **completely unaffected**. The DB schema is unchanged and the runtime path is identical.

- Combat system: no change.
- Space system: no change.
- Housing: no change (housing lots still live in the same `housing_lots` table, just written by the YAML loader now).
- Territory control: no change.
- Director AI: no change.
- Crafting, missions, bounties, factions, all command modules: no change.

### 7.2 Low-impact / Small-change

- **`engine/npc_loader.py`** — needs to read NPC placement from the YAML world loader instead of hardcoded `PLANET_NPCS`. The stat templates in `npcs_gg7.yaml` stay where they are.
- **`game_server.py`** — one-line swap: `load_world()` replaces `build_mos_eisley()` in the fresh-DB code path.
- **`engine/housing.py`** — housing lot definitions are loaded from YAML into the same tables they write to today. Housing CRUD untouched.
- **Tutorial quest chain** — if any tutorial code references rooms by integer ID (it shouldn't, but worth auditing), convert those to slug lookups via a new `db.get_room_id_by_slug()` helper.

### 7.3 Places to audit during Phase A extraction

These are the parts of the current script that encode world state in subtle ways. The extractor must capture each of them:

- Security zone assignment (`zones` table rows with security level).
- Map coordinates (`rooms.map_x`, `rooms.map_y`) — all 120 hand-tuned pairs.
- Hazard tagging on rooms (the v28 Survival Crafting Lane added ~20 hazard-tagged rooms — `hazard_type` in room properties JSON).
- Tutorial waypoint rooms.
- Housing `housing_id` column — only set at runtime when a player rents, not in the build, so no impact.
- Test character's full sheet (attributes, skills, force, equipment, inventory, tutorial state).

---

## 8. Failure Modes & Mitigations

**Risk: room ID reassignment breaks live content.**
Mitigation: §5.3 manifest check, plus the Phase B equivalence diff. Any ID change triggers a boot-time error, never a silent mismatch.

**Risk: YAML syntax errors during editing cause boot failure.**
Mitigation: the loader catches `yaml.YAMLError` and reports the file + line clearly. We also ship a `scripts/validate_world.py` that runs only the validation pass, for pre-commit checks.

**Risk: extraction produces non-equivalent output** (missed a field, lost a coordinate, miscounted housing lots).
Mitigation: Phase B diff is the gate. We cannot ship the cutover until the diff is clean.

**Risk: the `objects` table or other content** (items placed in rooms at build time) is forgotten.
Mitigation: Phase A audit lists every write performed by `build_mos_eisley.py`. If anything isn't in §7.3, it's a bug in the extractor.

**Risk: a builder reorders rooms in YAML and breaks references.**
Mitigation: manifest check fails the build with a clear error pointing to the reordered slug.

**Risk: slug collisions in the auto-generator** (e.g., two rooms named "Hallway").
Mitigation: collision suffixes during extraction (`hallway`, `hallway_2`), reviewed in Phase A commit.

---

## 9. Drop Plan

This is modestly scoped — smaller than Player Housing, about the size of Space Expansion v2 Phase 1. Estimated: 4 drops, 1 session total for Drops 1-3, 1 short follow-up session for cutover and cleanup.

### Drop 1 — Loader scaffold + YAML schemas

- `load_world.py` with stubs for each loader function.
- Empty `data/worlds/gcw/` with example `era.yaml` and one hand-written planet file as a schema-validation fixture.
- `validate_world()` implemented in full (§5.5).
- Unit tests for the validation pass.
- **No DB writes yet** — dry-run output only.

### Drop 2 — Extractor + generated YAML

- `scripts/extract_world_to_yaml.py` runs against `build_mos_eisley.py`.
- All YAML files generated under `data/worlds/gcw/`.
- `scripts/extraction_slug_map.json` committed.
- Human review pass — fix any slug oddities, confirm coordinates, verify NPC placements.

### Drop 3 — DB writers + equivalence test

- `insert_zones`, `insert_rooms`, `insert_exits`, `insert_npcs`, `insert_housing_lots`, `insert_test_character` implemented with transactional semantics.
- `scripts/diff_world_builds.py` implemented and passing.
- `rooms_manifest.json` generation.

### Drop 4 — Cutover + doc updates

- `game_server.py` boot path updated.
- `build_mos_eisley.py` → `build_mos_eisley_legacy.py`.
- Architecture doc updated: new §22 "World Content Loader" section, §4 updated to reference YAML paths.
- Session handoff doc.

---

## 10. After This Ships

With world content as data, the wilderness design doc can assume:

- A `data/worlds/<era>/wilderness/` directory is available for wilderness regions.
- New content types (wilderness regions, random encounter tables, terrain descriptions) slot into `era.yaml`'s `content_refs` cleanly.
- Wilderness-to-named-room edge connections live in YAML on both sides, not in two parallel Python dicts.
- A Clone Wars era is one directory copy away, with setting-specific content dropped into `data/worlds/clone_wars/` as and when we decide to ship it.

And the immediate, setting-independent win: adding or editing a room is a YAML diff, not a Python refactor. That alone compounds across every future content session.

---

## 11. Open Questions

1. **Should `era.yaml`'s `policy` section be enforced in v1, or just reserved for future use?** Recommendation: reserve, don't enforce. `force_chargen_allowed: false` is documented but not read by `force_powers.py` in this refactor. Wiring it up is a separate, later change.

2. **Do we ship a `@reload world` admin command?** Recommendation: no, not in v1. Hot-reload of world content into a live DB has too many invariants to get right in this scope (characters currently in rooms, exits being traversed, housing refs, etc.). Boot-time only is the safe answer.

3. **Should the loader generate `map_x`/`map_y` for rooms that omit them?** Recommendation: yes, via simple grid fallback per planet (current code already does this for rooms without hand-tuning). Validation warns about missing coordinates; loader provides sensible defaults.

4. **NPC template format — do we refactor `npcs_gg7.yaml` at the same time?** Recommendation: no. Scope creep. The world loader references existing template IDs; the template file stays as-is.

5. **Do we version the YAML format itself?** Recommendation: yes, with a top-level `schema_version: 1` in `era.yaml`. Cheap to add now, painful to retrofit later when v2 needs new fields.

---

*End of World Data Extraction Design Document — Version 1.0*
*Prerequisite refactor for: Wilderness system (next doc), future Clone Wars era content, any future world expansion.*
*References: `sw_d6_mush_architecture_v29.md`, `build_mos_eisley.py` (live source), `tutorial_bugfix_design_v1.md` (exit-collision history), existing data loaders in `data/species/`, `data/schematics.yaml`, `data/organizations.yaml`.*
