# Wilderness System — Design Document v1

**SW_MUSH · April 18, 2026 · Competitive Analysis Tier 4 item #21**

**Prerequisite:** `world_data_extraction_design_v1.md` must be delivered first. This doc assumes world content lives under `data/worlds/<era>/`.

---

## 1. Problem Statement

The Star Wars galaxy is defined by its empty places. The Dune Sea around Mos Eisley. The Jundland Wastes. The forests of Kashyyyk, the swamps of Dagobah, the ice fields of Hoth. These are *vast, dangerous, low-density* spaces where interesting things happen *because* they are vast and dangerous and low-density. Rebel bases hide in them. Smugglers land in them. Hermits retreat into them. They are the setting's negative space, and they matter.

SW_MUSH currently has no way to represent this. Our 120 hand-built rooms are dense, hand-authored, densely-meaningful locations — perfect for Mos Eisley's market, wrong for the Dune Sea. The `jundland_wastes` zone today is a handful of named rooms (Tusken Camp, Krayt Graveyard, Hidden Cave) reached through hand-authored exits. Going "into the wasteland" is a three-room walk to a specific named location. There is no actual *wilderness*.

The Evennia wilderness pattern solves this: instead of building a room per location, you define a coordinate grid per region, attach terrain metadata to coordinates, and generate the player's "current room" on demand from terrain rules. One region can represent thousands of square kilometers without 10,000 rows in the `rooms` table. Named landmarks (hidden bases, Rebel safehouses, homesteads) anchor at specific coordinates inside the grid. Edges connect to hand-built rooms at the region's perimeter.

**What this unlocks:**

- **Exploration as a gameplay loop.** Players walk into the wastes, navigate by compass and stamina, discover things.
- **Rebel hidden bases** as designed content, locatable only by Search rolls or by owners who know the coordinates.
- **Remote homesteads** (Tier 3 housing) anchored to wilderness, not to public hand-built rooms.
- **Environmental hazards at scale.** The Dune Sea *is* the hazard, not a single room with a dehydration timer.
- **Random encounters that matter.** Dewbacks, Tuskens, Jawa sandcrawlers, speeder bike raids — spawned on terrain and faction context.
- **Survival crafting demand.** The one remaining economic sink for Phase-28 survival gear.
- **Director-narrated wilderness arcs.** Sandstorm events, Imperial sweeps, Separatist landing parties.
- **A clean template for Clone Wars and future eras.** Wilderness regions are data; new settings get new regions.

**What it must not become:**

- A walking simulator where you move 200 squares to find nothing.
- An auto-generated description grinder where every tile reads like AI slop.
- A place that silently disconnects from the existing security/hazard/faction systems.
- A replacement for hand-built content — named places still matter more than terrain.

---

## 2. Design Principles

**1. Wilderness is content-sparse, event-dense.** Most tiles have no unique authored content — just terrain + weather + time. But the things that *do* happen in wilderness (landmarks, encounters, faction events) should be proportionally more significant than a cantina visit. You don't go into the desert for flavor text.

**2. Coordinates are the primary key.** A wilderness location is addressed by `(region_slug, x, y)`, not a room ID. Named landmarks within the grid are still rows in the `rooms` table (so homes, HQs, and quest content can anchor them), but they carry coordinate metadata and the wilderness pathing code treats them as tiles.

**3. Terrain + hand-author beats pure procedural.** Every tile has an authored *terrain type* (dune, rocky_outcrop, canyon, oasis). The description shown to players is composed from that terrain's description pool plus weather plus time-of-day plus any Director modifiers. It is not LLM-generated on the fly, but builders can author variants and the system rotates among them.

**4. Wilderness inherits zone security, usually "lawless."** Most wilderness is lawless by default. Faction-controlled wilderness (Imperial patrol zones, Republic-secured systems in Clone Wars) can override locally. No new security concepts; existing `engine/security.py` enforcement still works.

**5. Telnet-first, web-enhanced.** Wilderness must work on raw telnet. The web client gets a visual minimap; telnet players get a text compass + landmark directory. Text is canonical.

**6. Never block existing systems.** Combat, hazards, NPCs, Director AI, housing — all existing systems treat wilderness tiles identically to rooms. A wilderness tile *is* a room object to the rest of the engine at read-time. The novelty is where tiles come from, not what they are.

**7. One region per planet to start.** Dune Sea for Tatooine. The system should support many regions per planet, but launch with one well-tuned region rather than four mediocre ones.

---

## 3. Data Model

### 3.1 Region Definition (`data/worlds/<era>/wilderness/<region>.yaml`)

Each region is one file. Example: `data/worlds/gcw/wilderness/dune_sea.yaml`.

```yaml
region:
  slug: dune_sea
  name: "The Dune Sea"
  planet: tatooine
  zone: jundland_wastes        # existing zone, inherits security
  default_security: lawless
  narrative_tone_key: tatooine_wastes

grid:
  width: 40                    # x-coords 0..39
  height: 40                   # y-coords 0..39
  tile_scale_km: 2             # 2km per tile. 40x40 = 80km x 80km region
  default_terrain: dune        # tiles with no explicit assignment

# Terrain definitions. Each terrain is a description family.
# Actual display chosen at `look`-time from the variants pool.
terrains:
  dune:
    move_cost: 2               # stamina cost per move (see §4.3)
    sight_radius: 1            # tiles visible on look (see §4.5)
    ambient_hazard: extreme_heat
    hazard_severity: 2
    variants:
      - "Rolling dunes stretch in every direction. The sand shifts with each gust of wind."
      - "A sea of sand, sculpted by centuries of wind. The twin suns hammer down."
      - "Steep dunes rise and fall. Footprints vanish within minutes of being made."
    time_overlays:
      night: "Under the cold moonlight, the dunes take on a silver-blue cast. The heat has broken; the cold is coming."

  rocky_outcrop:
    move_cost: 3
    sight_radius: 2
    ambient_hazard: extreme_heat
    hazard_severity: 1
    variants:
      - "Weathered stone rises from the sand in broken ridges. Shadows pool in the crevices."
      - "A low rocky shelf juts from the desert floor, offering rare shade and footholds."

  canyon:
    move_cost: 2
    sight_radius: 1            # canyons are visually confined
    ambient_hazard: extreme_heat
    hazard_severity: 1          # less exposed
    variants:
      - "Wind-carved sandstone walls rise on either side, funneling the hot air."
    encounter_bias: [tusken_raiders, krayt_dragon]

  oasis:
    move_cost: 1
    sight_radius: 3
    ambient_hazard: none       # safe tile
    variants:
      - "An unlikely pool of water surrounded by hardy scrub. Life clusters here."
    landmark_eligible: true    # can host homesteads

  vaporator_field:
    move_cost: 2
    sight_radius: 2
    ambient_hazard: extreme_heat
    hazard_severity: 1
    variants:
      - "Moisture vaporators stand in uneven rows, their silver spires ticking in the heat."
    encounter_bias: [jawa_sandcrawler, moisture_farmer_npc]

# Tile map. Any tile not listed uses default_terrain.
# Sparse representation — authors only specify non-default tiles.
tile_assignments:
  - coords: [12, 14]
    terrain: oasis
  - coords: [15, 14]
    terrain: oasis
  - region_block:              # rectangular block
      x1: 20
      y1: 10
      x2: 24
      y2: 14
    terrain: canyon
  - region_block:
      x1: 5
      y1: 5
      x2: 8
      y2: 8
    terrain: rocky_outcrop

# Fixed landmarks. These are real rows in the rooms table,
# addressed by slug, with coordinates inside the region.
landmarks:
  - slug: krayt_graveyard
    name: "Krayt Graveyard"
    coords: [18, 22]
    description: |
      The bleached skeletons of ancient krayt dragons rise from the sand
      like the ribs of great ships. Wind moans through the bones.
    security_override: null    # inherit zone
    search_difficulty: 0       # visible without a roll
    fixed_encounters: [krayt_dragon_juvenile]
    faction: null

  - slug: tusken_encampment
    name: "Tusken Encampment"
    coords: [26, 7]
    description: |
      A ring of hide tents around a banked fire. Banthas are tethered
      nearby. Tusken Raiders move with purpose between the tents.
    search_difficulty: 10      # moderate search to find if not already known
    fixed_encounters: [tusken_raider_warband]
    faction: tusken

  - slug: rebel_watchstation_4
    name: "Concealed Observation Post"
    coords: [30, 30]
    description: |
      A camouflaged bunker dug into the side of a dune, its viewport
      barely visible. Antennas poke from the sand.
    search_difficulty: 20      # hard to find
    visibility:
      faction_known: [rebel]   # rebel members see it on the map automatically
      coords_hint_known: []    # PCs who have been told the coords can navigate to it
    faction: rebel
    housing_lot: rebel_hq_dune_sea

# Edge connections to hand-built rooms at the region perimeter.
edges:
  - room_slug: outskirts_east_checkpoint   # existing hand-built room
    coords: [0, 20]                         # enter the grid here
    direction_from_room: "southeast"        # player types "southeast" in the room
    direction_back_to_room: "west"          # player types "west" from (0,20)
    enter_message: "You step past the checkpoint and onto the open sand. Mos Eisley recedes behind you."
    exit_message: "The town of Mos Eisley rises on the horizon. The checkpoint guard nods as you pass."

  - room_slug: jundland_canyon_trailhead
    coords: [22, 12]
    direction_from_room: "into the sands"
    direction_back_to_room: "back to the trail"

# Random encounter table. Weighted by terrain.
# Full encounter design in §5.
encounters:
  base_chance_per_move: 0.04   # 4% of entering a tile triggers an encounter check
  table:
    - id: dewback_herd
      weight: 20
      terrains: [dune, rocky_outcrop]
      npc_template: dewback
      count: [2, 4]
      hostile: false

    - id: tusken_war_party
      weight: 8
      terrains: [dune, canyon]
      npc_template: tusken_raider
      count: [3, 5]
      hostile: true
      min_distance_from_edge: 8  # don't spawn right next to city

    - id: sandstorm_event
      weight: 5
      terrains: [dune, rocky_outcrop]
      type: weather
      effect:
        forced_hazard: sandstorm
        duration_minutes: 15

    - id: imperial_patrol_skiff
      weight: 4
      terrains: [dune]
      faction_gate: { empire_presence_min: 3 }   # only when Imperial influence in zone is high
      npc_template: sandtrooper
      count: [2, 3]
      behavior: patrol

    - id: jawa_sandcrawler
      weight: 6
      terrains: [dune, vaporator_field]
      type: trader_caravan
      npc_template: jawa_merchant
      count: [4, 6]
      hostile: false

    - id: derelict_speeder
      weight: 3
      terrains: [dune, rocky_outcrop]
      type: anomaly
      salvage_loot_table: desert_derelict
```

This file format deliberately mirrors the data extraction doc's conventions — slug-based references, zone inheritance, YAML block scalars for descriptions.

### 3.2 DB Schema

Two new tables; no changes to existing tables except one additive column on `rooms`.

```sql
-- Wilderness regions (one row per region loaded from YAML)
CREATE TABLE IF NOT EXISTS wilderness_regions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    slug            TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    planet          TEXT NOT NULL,
    zone_slug       TEXT NOT NULL,
    width           INTEGER NOT NULL,
    height          INTEGER NOT NULL,
    tile_scale_km   INTEGER NOT NULL DEFAULT 1,
    default_terrain TEXT NOT NULL,
    default_security TEXT NOT NULL,
    config_json     TEXT NOT NULL DEFAULT '{}',   -- full region YAML, cached for fast lookup
    created_at      REAL NOT NULL
);

-- Persistent player position within wilderness (extends characters)
-- We add a nullable column to characters instead of a new table, keeping the
-- "one authoritative location" invariant.
ALTER TABLE characters ADD COLUMN wilderness_region_id INTEGER DEFAULT NULL;
ALTER TABLE characters ADD COLUMN wilderness_x INTEGER DEFAULT NULL;
ALTER TABLE characters ADD COLUMN wilderness_y INTEGER DEFAULT NULL;
-- When wilderness_region_id IS NOT NULL, the character is in wilderness and
-- room_id is set to the virtual wilderness room sentinel (see §4.1).

-- Discovered-landmark tracking: which characters know which hidden landmarks
CREATE TABLE IF NOT EXISTS wilderness_discoveries (
    char_id         INTEGER NOT NULL,
    landmark_slug   TEXT NOT NULL,
    discovered_at   REAL NOT NULL,
    PRIMARY KEY (char_id, landmark_slug),
    FOREIGN KEY (char_id) REFERENCES characters(id)
);

-- Landmarks are rows in the existing rooms table, marked by a new column
ALTER TABLE rooms ADD COLUMN wilderness_region_id INTEGER DEFAULT NULL;
ALTER TABLE rooms ADD COLUMN wilderness_x INTEGER DEFAULT NULL;
ALTER TABLE rooms ADD COLUMN wilderness_y INTEGER DEFAULT NULL;
-- When these are non-null, this room is a landmark inside a wilderness region.
```

**Design choices worth calling out:**

- **No per-tile rows.** A 40x40 region is 1,600 tiles; we don't materialize them. The region config + terrain rules are sufficient to compute any tile's state on demand.
- **Landmarks are real rooms.** Hidden bases, homesteads, and Rebel outposts live in the `rooms` table so housing, quest, NPC, and combat systems treat them normally. They just also have coordinates.
- **Character has a single location.** Either `room_id` (normal room) or `wilderness_region_id + x + y` (virtual wilderness tile). Never both meaningfully set.
- **Discoveries are per-character.** One player finding a hidden base doesn't reveal it to everyone. Faction membership grants visibility via `visibility.faction_known` (checked at render time, no DB flag).

### 3.3 Virtual Room Sentinel

Every wilderness region gets a single row in `rooms` with `slug = wilderness_<region_slug>_virtual` — a sentinel that characters' `room_id` points to when they're in wilderness. This preserves the invariant that `characters.room_id` is always a valid room.

Rendering looks up `(wilderness_region_id, x, y)` on the character and calls the wilderness renderer instead of using the sentinel's description. The sentinel room itself is never displayed; it just parks the foreign key.

This is the same pattern used by ship interiors today (characters sitting in a ship have `room_id` pointing to a bridge room, which is real).

---

## 4. Runtime Behavior

### 4.1 Entering Wilderness

A player in `outskirts_east_checkpoint` types `southeast` (or `into the sands`). The movement system sees that this room has a wilderness edge defined:

1. The mover resolves to the edge entry: `(dune_sea, 0, 20)`.
2. The character's `room_id` is set to the Dune Sea sentinel room.
3. `wilderness_region_id`, `wilderness_x`, `wilderness_y` are set to `(dune_sea.id, 0, 20)`.
4. The edge's `enter_message` plays.
5. `look` is invoked (see §4.4).

Leaving is symmetric: at `(0, 20)` the player types `west`, which resolves via the edge back to the checkpoint room.

### 4.2 Movement Within Wilderness

Cardinal directions work as expected: `north` = y+1, `south` = y-1, `east` = x+1, `west` = x-1. Diagonals combine. The movement handler:

1. Computes the destination `(x', y')`.
2. Checks bounds against region `width`/`height`. Out-of-bounds fails unless the tile is an edge connection — in which case the movement lands them back in the connected room.
3. Checks terrain `move_cost` for the destination tile and debits stamina (see §4.3).
4. Runs encounter roll (§5).
5. Updates `(wilderness_x, wilderness_y)`.
6. Triggers `look`.

**Named-direction movement** (to a known landmark): `travel krayt_graveyard` finds the straight-line path and moves one tile toward it per invocation. Landmark slug must be visible to the character (not hidden, or already discovered, or faction-revealed). This is a comfort command for telnet players who don't want to type `east east east east east southeast southeast`.

### 4.3 Stamina / Move Cost

Each tile move consumes a small stamina pip based on terrain `move_cost`. This is the existing Stamina mechanic from the Survival Crafting Lane, not a new resource:

- `move_cost: 1` (oasis, trail) — negligible drain.
- `move_cost: 2` (dune, vaporator_field) — normal desert travel.
- `move_cost: 3` (rocky_outcrop, mountain) — hard going.

Every N moves (N = 10 by default) without rest, the character rolls a Stamina check vs. a difficulty set by the region's cumulative `hazard_severity` since last rest. Failure applies a Stunned condition; critical failure applies Wounded.

**Water/food items** (`water_canteen`, `ration_pack`) reset the check counter when consumed. This wires directly into Phase-28 survival crafting — breath masks, cooling units, water canteens all matter here.

**Resting** (new command, `rest` while in wilderness) advances time-of-day, clears the move counter, and has a chance to trigger a nighttime encounter. Resting in an oasis is safe; resting on an open dune is dangerous.

### 4.4 Looking at a Wilderness Tile

When a player types `look` in wilderness:

1. Resolve the terrain for `(x, y)` — tile assignments or `default_terrain`.
2. Pick a description variant (deterministic: hash `(region_id, x, y, weather_state)` and index into variants — same tile reads the same way each visit, different tiles read differently).
3. Apply time-of-day overlay if present.
4. Apply weather state if present (sandstorm, night).
5. List visible landmarks within `sight_radius` tiles.
6. List visible characters (same rules as rooms — other PCs, NPCs in the same tile).
7. Build the "exits" display: cardinal directions showing terrain types of adjacent tiles.

Example output:

```
The Dune Sea — Coordinates 12, 18
  Rolling dunes stretch in every direction. The sand shifts with each
  gust of wind. The twin suns hammer down mercilessly.

  [LAWLESS]
  Movement: dune (cost 2)  Stamina: 8/10  Water: 1 canteen

  You see in the distance:
    - An unlikely pool of water surrounded by scrub (south, ~4km)
    - The bleached skeletons of great beasts (east, ~12km)

  Terrain around you:
    north: dune        south: rocky_outcrop
    east:  dune        west:  dune
```

The "distance" readout is `sqrt(dx^2 + dy^2) * tile_scale_km` rounded to nearest km. Landmark visibility within `sight_radius` is computed by Euclidean distance. Sight radius is bounded by terrain — canyons hide distant things.

### 4.5 Visibility and Discovery

Three visibility rules, applied in order:

1. **Always visible:** landmarks with `search_difficulty: 0`. No roll needed.
2. **Faction-revealed:** landmarks where `visibility.faction_known` includes the character's faction. Rebels see Rebel bases. Imperials see Imperial outposts.
3. **Discovered:** landmarks the character has a row for in `wilderness_discoveries`. Discovery happens three ways:
   - Active search: `search` command in a tile runs a Search check vs. `search_difficulty` for each hidden landmark within `sight_radius`. Success records the discovery.
   - Intel: another character shares coordinates via a new `share coords <landmark>` command. The recipient gets a discovery row.
   - Quest hooks: completing a mission that reveals a base auto-grants discovery.

Hidden landmarks within sight radius of the character's tile but not discovered appear as anomalous readings on the web minimap ("? unknown") — just enough hint that a good search might find something. Telnet gets a text cue: "Something in this area doesn't look right. Try searching."

---

## 5. Encounters

Encounters are the engine that makes wilderness feel alive. The existing `engine/npc_combat_ai.py`, NPC spawning, and anomaly systems are reused; this section defines how wilderness chooses *which* encounter to fire.

### 5.1 Encounter Roll on Move

Every tile entry rolls against `base_chance_per_move` (default 4%). A roll under the threshold triggers encounter selection:

1. Filter the encounter table by the destination tile's terrain (`terrains:` matches).
2. Filter by `faction_gate` conditions (e.g., Imperial patrols only when Imperial zone influence is high).
3. Filter by `min_distance_from_edge` (no tusken war parties two tiles from town).
4. Weighted-random select from the filtered set.
5. Spawn the encounter.

If no encounters match filters, move proceeds normally (silence is fine; not every tile is eventful).

### 5.2 Encounter Types

Four types already supported by existing systems, plus one new:

- **`hostile`** — NPC(s) spawn on the tile and initiate combat via existing `engine/npc_combat_ai.py`. Tier derives from region default or encounter override.
- **`non_hostile`** — NPC(s) spawn but don't aggro. Dewback herds, scavenger droids, wandering Jawas.
- **`trader_caravan`** — Non-hostile NPC(s) carrying a vendor inventory. Jawa sandcrawler stops, haggles, moves on. Tied to existing vendor droid / shop infrastructure.
- **`anomaly`** — Reuses `engine/space_anomalies.py` pattern: a derelict speeder, abandoned moisture vaporator, crashed escape pod. Salvage rolls drop resources and credits.
- **`weather`** (new) — Region-wide or tile-local effect. Sandstorm forces `hazard: sandstorm` on nearby tiles for N minutes, reducing sight radius to 0 and increasing hazard severity. Applied via the existing buff/debuff handler.

### 5.3 Faction-Driven Encounters

The `faction_gate` field lets encounters respond to Director AI state. Imperial patrols appear when Imperial influence in the containing zone is high. Separatist landing parties appear in Clone Wars content when Separatist presence is non-zero. Rebel scouts in GCW appear to non-Rebels as hostile and to Rebels as friendly.

This means the *same region* feels different depending on faction dynamics. After a Director-narrated Imperial crackdown, Dune Sea traffic doubles and Tuskens go quiet. After a Rebel operation, Rebel faces appear and Imperials hunt them. No new content authored; the existing Director faction-turn outputs drive the encounter weights.

### 5.4 Encounter Cooldown Per Character

To prevent encounter fatigue from pacing back and forth, each character has a per-region encounter cooldown: once an encounter fires, no further encounter checks roll for that character for the next 60 seconds (configurable). This is a transient in-memory flag, not a DB field.

---

## 6. Integration with Existing Systems

### 6.1 Security

Wilderness tiles inherit the containing zone's security level. The `default_security` field on the region is a safety net; individual landmarks can override via `security_override` (a Rebel base is `contested` even in a `lawless` region, by Rebel claim).

`get_effective_security()` in `engine/security.py` gets a new case: if the character is in wilderness, look up `(region, x, y)` and return the relevant security level. No changes to callers — combat, NPC aggro, and PvP checks work identically.

### 6.2 Hazards

`engine/hazards.py` (v28 Survival Crafting Lane) already supports per-room hazard tagging. Wilderness extends it: `terrain.ambient_hazard` + `hazard_severity` feed the same hazard check loop. The same mitigation items (water, breath masks, cooling units) apply.

The hazard tick, which currently iterates `rooms` with occupants, gains a parallel path iterating characters with non-null `wilderness_region_id`. Same timers, same checks, same output.

### 6.3 Housing — Remote Homesteads

A new Tier 3 housing variant: `private_homestead`. Like a standard private residence but anchored at a wilderness coordinate instead of an `entry_room_id`. Buying a homestead creates a landmark row in `rooms` with `wilderness_region_id/x/y` set, and the home's interior rooms are additional regular rooms linked via a single exit from the landmark.

The `housing_lots.yaml` file gets a new lot type:

```yaml
- slug: dune_sea_homestead_1
  tier: 3
  wilderness:
    region: dune_sea
    coords: [24, 26]
    search_difficulty: 10    # moderate — neighbors can find you if they look
  planet: tatooine
  zone: jundland_wastes
```

Real estate NPCs on Tatooine gain a "remote homestead" product alongside the existing city properties. Owners can invite guests via the normal housing guest list; guests get a `wilderness_discoveries` row for the landmark so they can navigate back.

### 6.4 Housing — Faction HQs

Tier 5 faction HQs (existing design) gain a wilderness variant: `faction_hq_remote`. Rebel cells especially benefit — a hidden base in the Dune Sea with `search_difficulty: 20` and `visibility.faction_known: [rebel]` is exactly the "Rebel Base Construction" pattern from the Star Wars Sourcebook.

The faction HQ purchase flow is unchanged; the admin `@faction hq create` command gains a wilderness-mode flag that picks a coordinate within a region.

### 6.5 Territory Control

The existing `engine/territory.py` operates on zones and hand-built rooms. For wilderness, we add regional territory influence — the whole Dune Sea region carries a single faction-influence tuple that updates based on faction-owned landmarks within it. One Imperial outpost plus three Rebel hidden bases tilts influence toward Rebel.

This is deliberately coarse: wilderness territory isn't tile-by-tile claimable. That would invite tedious PvP and micro-management. The landmark-driven regional tilt is enough signal for the Director AI and for `faction status` displays.

### 6.6 Director AI

The Director gets two new capabilities:

- **Wilderness digest items.** The daily digest includes per-region traffic summaries ("12 Dune Sea crossings today, 3 Tusken encounters, 1 discovered landmark") feeding the Director's narrative context.
- **Wilderness event generation.** The Director can fire region-scoped events: "Imperial Dragnet" raises the Imperial patrol encounter weight in Dune Sea for 6 hours. "Sandstorm Season" applies rolling weather across all terrains for a week. Events are scoped to `region_slug` the same way existing Director events are scoped to zones.

### 6.7 Crafting

Wilderness enables the survival-gear demand that v28's Survival Crafting Lane was half-missing. Water canteens, cooling units, breath masks, ration packs, and sandblaster goggles all have clear value the moment you walk into a region. No new schematics required in v1; the existing ones suddenly matter.

A stretch goal: wilderness-only *harvestable resources*. Certain tiles at certain times (oasis at dawn, canyon after rain) yield gathered resources via a new `harvest` command. Scope this out of v1 — implement after the core region system is stable.

### 6.8 Space Integration

Landing a ship in wilderness is a natural capability but a big scope expansion. **Out of scope for v1.** Ships land at existing dock rooms; characters walk into wilderness from there. If demand arises, a later drop can add `land_here` as a wilderness command that spawns a landed-ship landmark at the character's coords.

---

## 7. Web Client Integration

### 7.1 Minimap Panel

A new context-panel section when the character is in wilderness: a 2D minimap of the surrounding tiles (5x5 or 7x7 centered on the player). Terrain types render as colored cells:

- Yellow: dune
- Brown: rocky_outcrop
- Dark yellow: canyon
- Blue: oasis
- Gray: rocky_outcrop / mountain
- Green dot: oasis / vaporator field

Visible landmarks show as icons. Hidden (within sight radius but undiscovered) show as `?`. The player's tile is center, highlighted.

Clicking an adjacent tile moves there. Clicking a visible landmark triggers `travel <slug>`.

### 7.2 Compass Display

Telnet-compatible text compass:

```
      N
     ^
W  <-+->  E
     v
      S
```

With terrain annotations on each adjacent. The web client renders this as a cleaner compass widget but sends the same data.

### 7.3 Stamina/Water Bars

New HUD elements: stamina bar (already present from combat, reused), water pack count, hazard severity indicator. When hazard severity is high, the indicator pulses.

### 7.4 Mood Integration

The ambient mood system (zone-keyed CSS custom properties) extends to wilderness: terrain type adjusts the mood accent. Sandstorm weather tint is a rust-orange wash. Nighttime wilderness shifts to cool blue.

---

## 8. Commands

### 8.1 Player Commands

| Command | Function |
|---------|----------|
| `<direction>` | Move one tile. Cardinals + diagonals. |
| `travel <landmark>` | Walk one tile toward a known landmark. |
| `look` | Render current tile (§4.4). |
| `look <direction>` | Preview adjacent tile terrain + visibility. |
| `search` | Search for hidden landmarks in sight radius. Skill check. |
| `rest` | Rest at current tile. Advances time, clears move counter. Encounter risk. |
| `coords` | Show current coordinates (useful for coordinating with other players). |
| `share coords <landmark> with <player>` | Transfer a landmark discovery. |
| `landmarks` | List landmarks the character knows in the current region. |
| `wilderness exits` | Show edge connections back to named rooms. |

### 8.2 Admin/Builder Commands

| Command | Function |
|---------|----------|
| `@wilderness reload <region_slug>` | Reload a region's YAML (dev only). |
| `@wilderness tp <region> <x> <y>` | Teleport into a region. |
| `@wilderness grid` | Show the full region grid with all landmarks (ASCII map). |
| `@wilderness reveal <player> <landmark>` | Grant a discovery manually. |
| `@wilderness landmark add <region> <slug> <x> <y>` | Create a landmark in a live region (persists to DB, not YAML — review/commit separately). |

---

## 9. Validation

The loader for wilderness YAML runs these checks at boot:

1. Region slug unique across all regions.
2. Coordinates in range for all landmarks and edges.
3. All `zone_slug` and `planet` references resolve.
4. Every landmark's `housing_lot` (if set) exists in housing lots.
5. Every encounter's `npc_template` resolves in `npcs_gg7.yaml` or wilderness-local NPC table.
6. Every edge's `room_slug` exists in the world content.
7. No two landmarks share coordinates within the same region.
8. `search_difficulty`, `move_cost`, `sight_radius` within sensible bounds.
9. Encounter weights positive and at least one encounter matches every terrain in the region (otherwise that terrain's tiles never fire encounters).

Warnings (non-fatal):

- Regions with no edges (unreachable).
- Terrains with no description variants (falls back to a generic string).
- Landmarks with very high `search_difficulty` and no faction visibility (never findable in practice).

---

## 10. Drop Plan

Seven drops, scoped conservatively. Estimate: ~2 sessions.

### Drop 1 — Schema + Region Loader

- `wilderness_regions`, `wilderness_discoveries` tables; `rooms` ALTER; `characters` ALTER.
- YAML loader in `load_world.py` reading `data/worlds/<era>/wilderness/*.yaml`.
- Validation pass (§9).
- Dune Sea authored as the first region YAML (~40x40 with ~8 terrain assignments, 3 landmarks, 2 edges, 6 encounter types).
- No runtime behavior yet; just load + validate.

### Drop 2 — Core Movement + Look

- Virtual room sentinels on region load.
- Movement handler: cardinal + diagonal, bounds, edge entry/exit.
- `look` renders tile (§4.4) with terrain variants, time overlay, adjacent-tile preview.
- `coords`, `landmarks`, `wilderness exits` commands.
- No hazards, no encounters, no search yet. Just: can walk into the Dune Sea, move around, see terrain, walk back out.

### Drop 3 — Hazards + Stamina

- Move-cost stamina drain.
- Wilderness hazard tick wired to `engine/hazards.py`.
- Water/ration item consumption resets counters.
- `rest` command.
- `look` shows stamina and hazard state.

### Drop 4 — Landmarks + Search + Discovery

- Visible landmarks render within sight radius.
- `search` command with Search skill check.
- `wilderness_discoveries` tracking.
- `share coords` command.
- Faction visibility rules.
- `travel <landmark>` movement aid.

### Drop 5 — Encounters

- Encounter roll on move.
- Table-driven encounter selection (terrain, faction gate, distance).
- Hostile spawns via existing NPC combat AI.
- Non-hostile spawns (dewbacks, sandcrawlers).
- Weather encounters (sandstorm as first implementation).
- Per-character cooldown.

### Drop 6 — Web Minimap + HUD

- 5x5 minimap in context panel.
- Landmark icons, fog of war for undiscovered.
- Click-to-move on adjacent tiles.
- Stamina + water HUD elements.
- Wilderness mood integration.

### Drop 7 — Housing + Faction HQ Wilderness Variants

- New housing types: `private_homestead`, `faction_hq_remote`.
- Real estate NPC flow for remote homesteads.
- Faction HQ wilderness placement via admin.
- Landmark ↔ housing_id linkage.
- Regional faction influence signal in territory.py + Director digest.

**Post-launch follow-up (not in v1):**

- Additional regions: Nar Shaddaa rooftops, Kessel surface, Corellian agricultural belt.
- Harvestable resources.
- Ship-landing in wilderness.
- Procedural named-tile ambient flavor (LLM-authored variants vetted at build time).

---

## 11. Failure Modes & Mitigations

**Risk: Empty-desert problem.** Players walk 30 tiles and nothing happens; they quit. Mitigation: encounter rate tuned up at launch (6-8% vs 4% baseline), reduced if playtesting shows it's excessive. Also: landmark density in the initial Dune Sea is 3 per 1,600 tiles, which is sparse; target 6-10 for the shipped version so there's always something within sight radius.

**Risk: Encounter spam.** Characters get jumped every other tile and can't actually explore. Mitigation: per-character cooldown (§5.4), minimum distance from edge for hostile encounters, weighted toward non-hostile encounters early in the table.

**Risk: Hidden landmarks are *too* hidden.** Players never find the Rebel base because `search_difficulty: 20` is stochastically impossible for low-Perception characters. Mitigation: mission/quest hooks grant discovery outside the search roll; faction visibility grants automatic discovery for relevant faction members; admin commands to reveal as a GM option.

**Risk: Wilderness makes existing zone systems inconsistent.** Someone designs a quest that references a hand-built room, and it accidentally spawns someone in wilderness. Mitigation: virtual sentinel rooms are clearly named (`wilderness_<region>_virtual`) and flagged with a property so misuse throws a clear error. All `db.get_room()` calls continue to work normally.

**Risk: Stamina grind becomes a chore.** Moving across a 40x40 region costs too much stamina and players quit. Mitigation: tile sizes tuned so a full region crossing is ~20 moves, not 40. Oasis tiles restore stamina. Riding a dewback (future feature) halves move cost.

**Risk: The `look` description pool feels samey.** Every tile reads the same three strings. Mitigation: authored 6-10 variants per terrain, with time-of-day and weather overlays multiplying the effective pool. Hash-based selection means the same tile reads consistently, so players don't notice the pool depth.

**Risk: Web client can't handle the minimap data well on mobile.** Mitigation: minimap is an enhancement; telnet text compass is canonical. Mobile fallback is the text compass.

**Risk: Adding wilderness breaks housing/territory save data.** Mitigation: all schema changes are additive (new tables, nullable columns). Existing housing and territory records continue working unchanged. Wilderness-variant housing is new; no migration of existing housing.

---

## 12. Open Questions

1. **Should wilderness coordinates be globally unique or per-region?** Recommendation: per-region. `(region_id, x, y)` is the addressable tuple. A global coordinate space would imply world-scale geometry we don't want to commit to. Per-region is simpler and isolates design changes.

2. **Should `search` succeed partially?** Finding one hidden landmark out of three in sight radius is plausible. Recommendation: yes. On success, roll each hidden-in-range landmark independently against the Search result; any that pass become discovered. Encourages repeated searching.

3. **Should players be able to set their own wilderness landmarks (flags, beacons)?** Recommendation: defer. This is map-graffiti territory and invites abuse. Consider post-launch if players request it.

4. **Wilderness PvP rules?** Two players meet on the same tile. Recommendation: use the existing zone security level. Lawless wilderness allows PvP with one-time entry warning (matching the existing lawless-zone pattern). Contested wilderness requires a challenge. This is free; no new logic needed.

5. **Can NPCs traverse wilderness autonomously?** E.g., Jawa sandcrawlers roaming between tiles. Recommendation: not in v1. Encounters spawn, engage, and despawn in place. Moving NPCs inside wilderness is a nice-to-have that doesn't pay for itself in complexity.

6. **Do we persist encounter state across restart?** If a tusken war party is mid-combat when the server restarts, does it re-spawn on reboot? Recommendation: no. Encounters are transient. On restart, wilderness tiles reset to terrain-default, and characters mid-wilderness are where they left off (coords persist). This matches how space anomalies behave today.

7. **Should terrain variants be LLM-generated at region load time?** Haiku could generate 20 variants per terrain type from a seed prompt. Recommendation: not in v1, but keep the option open. Authored variants feel better on average; LLM expansion is a nice tool for builders to reach into later.

8. **Can the tutorial reference wilderness?** Sending new players into the Dune Sea in tutorial is an option. Recommendation: only as an optional advanced chain ("Explorer" profession). Core tutorial stays in hand-built rooms. Wilderness is advanced content.

---

*End of Wilderness System Design Document — Version 1.0*
*Prerequisite: World Data Extraction (`world_data_extraction_design_v1.md`) must be delivered before Drop 1 of this system begins.*
*References: `sw_d6_mush_architecture_v29.md`, `competitive_analysis_feature_mining_v1.md` (feature #21), `engine/hazards.py` (v28), `engine/security.py`, `engine/territory.py`, `engine/space_anomalies.py` (reuse pattern), `player_housing_design_v1.md` (Tier 3 and Tier 5 extensions), `organizations_factions_design_v1.md` (faction visibility rules), Evennia wilderness contrib (coordinate grid pattern), Star Wars Sourcebook Rebel Base Construction chapter, Galaxy Guide 7: Mos Eisley (Tatooine Wilderness).*
