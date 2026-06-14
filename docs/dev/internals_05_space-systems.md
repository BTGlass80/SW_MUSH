# Developer Internals — Guide_05_Space_Systems.md

Extracted from `data/guides/Guide_05_Space_Systems.md` during the help-guides rework (PRELAUNCH.help_guides_rework, Phase A). This is the developer-facing track that used to live inline in the player guide; it is NOT player-facing and is NOT loaded by the game. Treat it as reference docs, and re-verify any file:line citation against HEAD before trusting it.

---

### 🔧 Developer Internals

**File:** `engine/npc_space_traffic.py` — `ZONES` dict defines the complete zone graph with adjacency, zone types, planet keys, hazard flags, and environment strings. Zone IDs are integers; zone keys are strings.

**Room indexing:** Rooms are indexed by planet blocks (0–39 Tatooine, 40–54 Nar Shaddaa, 55–64 Kessel, 65–76 Corellia). `LandCommand` is planet-aware via the space zone's `.planet` field.

### 🔧 Developer Internals

**File:** `data/starships.yaml` (~400 lines, 19 templates including aliases). Each template defines: `name`, `nickname`, `scale`, `hull`, `shields`, `speed`, `maneuverability`, `crew`, `passengers`, `cargo`, `consumables`, `hyperdrive`, `hyperdrive_backup`, `cost`, `mod_slots`, `reactor_power`, and `weapons[]` (each with `name`, `fire_arc`, `damage`, `fire_control`, `skill`).

**Alias pattern:** Some templates have two keys (e.g., `yt_1300` and `yt1300`) because different code paths use different naming conventions. Both point to identical stats.

**`get_effective_stats(ship)`:** Template stats are never permanently modified. Installed mods are stored in the ship's systems JSON, and effective stats are computed at read-time by adding mod bonuses to template base values. This is a key architecture pattern — all stat queries go through this function.

### 🔧 Developer Internals

**File:** `parser/space_commands.py` — Station commands (`PilotCommand`, `GunnerCommand`, etc.) each set the player's station in the ship's crew tracking. `VacateCommand` clears it. `AssistCommand` implements copilot's +1D bonus.

**File:** `engine/npc_crew.py` / `engine/npc_space_crew.py` — NPC crew management, wage deduction (4-hour tick), station assignment, skill dice used for rolls.

### 🔧 Developer Internals

**`CourseCommand`** — Pilot-only. Checks zone adjacency in the zone graph, sets transit state in ship systems JSON, tick-based arrival. Piloting check on arrival determines how cleanly you enter the zone.

**`HyperspaceCommand`** — Travel time formula based on lane distance × hyperdrive multiplier. Transit state tracked in systems JSON. Tick hook checks arrival. `HYPERSPACE_DEST_TO_ZONE` mapping resolves destination names to zone keys.

**`LandCommand`** — Planet-aware via space zone's `.planet` field. Finds the appropriate docking bay room for the planet via `PLANET_BAY_SEARCH`. Triggers `auto_build_if_needed()` for dynamically-built rooms.

### 🔧 Developer Internals

**File:** `engine/starships.py` — Core space combat resolution:

**`SpaceGrid` class** (line 168): Manages pairwise range, relative position, speed, maneuver bonuses, and lock-on bonuses between all ships in a zone.
- `resolve_maneuver()` — Opposed piloting rolls with speed advantage (+1D per speed point). Actions: close, flee, tail, outmaneuver
- `add_lockon()` / `get_and_consume_lockon()` — Lock-on tracking, max +3D
- `set_maneuver_bonus()` / `get_and_consume_maneuver_bonus()` — Evasive difficulty bonus (one-shot per round)

**`SpaceRange` IntEnum**: CLOSE(0), SHORT(5), MEDIUM(10), LONG(15), EXTREME(25) — values are the difficulty modifier added to base gunnery difficulty.

**Fire arc system:** `can_weapon_fire(weapon_arc, relative_pos)` checks if a weapon's arc can reach the target's relative position (FRONT/REAR/FLANK). Turret weapons always fire.

**`resolve_evade()`** — Pilot skill + maneuverability vs. Moderate(10), with engine damage penalties (+5 for damaged, impossible for destroyed).

**Damage resolution** follows the ground combat pattern: weapon damage vs. hull + shields, with margin determining system damage. Ship systems (engines, weapons, shields, sensors, hyperdrive) can be individually damaged or destroyed.

### 🔧 Developer Internals

Power allocation is transient (stored in systems JSON). Default allocation on boot. Engineer station required to change. Each system has a power cost and a performance multiplier based on allocated power vs. required power.

### 🔧 Developer Internals

8 tactical order types defined in the space expansion addendum. Commander issues via `OrderCommand`, resolved through `resolve_coordinate_check()` in `skill_checks.py`. Orders stored in ship state and applied as modifiers during crew skill rolls.

### 🔧 Developer Internals

**File:** `engine/trading.py` (~335 lines):
- `TradeGood` dataclass: `key`, `name`, `base_price`, `description`, `source[]`, `demand[]`, `tons_per_unit`
- `TRADE_GOODS` dict: 8 goods with planet-specific source/demand lists
- Price tiers: `PRICE_SOURCE = 0.50`, `PRICE_NORMAL = 1.00`, `PRICE_DEMAND = 2.00`
- Cargo stored in ship's `cargo` JSON column as `[{"good": "raw_ore", "quantity": 50, "purchase_price": 50}, ...]`

Bargain checks route through `skill_checks.py::resolve_bargain_check()`.

### 🔧 Developer Internals

`TransponderCommand` in `parser/space_commands.py`. Countermeasure items crafted via the crafting system (Sensor Mask and Comm Jammer schematics in `data/schematics.yaml`).

### 🔧 Developer Internals

**File:** `engine/space_anomalies.py` (~325 lines):
- `ANOMALY_TYPES` list: 7 types with spawn weights, scan thresholds, and three description tiers (vague/partial/full)
- Module-level state dict (no DB) — `_anomalies: dict[str, list[Anomaly]]` keyed by zone
- `spawn_anomalies_for_zone()` — Called from tick (every 300 ticks)
- `get_anomalies_for_zone()` / `get_scan_result_text()` — Used by `DeepScanCommand`
- `tick_anomaly_expiry()` — Prune stale entries

### 🔧 Developer Internals

Mods stored in ship's systems JSON. `get_effective_stats()` is the single entry point for all stat queries — adds mod bonuses to template base values. 7 component schematics defined in `data/schematics.yaml`.

### 🔧 Developer Internals

**File:** `engine/ships_log.py` (~266 lines):
- `DEFAULT_LOG` dict: 11 tracking categories
- `MILESTONES` list: 17 milestone definitions with `category`, `threshold`, `cp` reward, optional `title`, and `msg`
- Stored in character attributes JSON under `"ships_log"` key
- `check_milestones()` compares current log values against thresholds, awards CP via existing `CPEngine` tick system

### 🔧 Developer Internals

**File:** `engine/npc_space_traffic.py` (~1,900 lines) — The largest single engine file. Manages NPC ship spawning, zone-to-zone transit, patrol encounters, pirate attacks, customs inspections, and per-zone ship caps to prevent spam.

### 🔧 Developer Internals

`build_space_state()` and `broadcast_space_state()` helpers in `parser/space_commands.py` serialize the complete space state for WebSocket delivery. Send points wired into LaunchCommand, LandCommand, FireCommand, ShieldsCommand, hyperspace/sublight arrival ticks.

## 16. File Reference

| File | Lines | Purpose |
|------|-------|---------|
| `parser/space_commands.py` | ~5,184 | 49+ space commands, combat flow, HUD serialization |
| `engine/starships.py` | ~1,892 | Ship templates, SpaceGrid, combat resolution, maneuvers, evade |
| `engine/npc_space_traffic.py` | ~1,900 | NPC ship spawning, zone transit, patrols, pirates, customs |
| `engine/trading.py` | ~335 | 8 trade goods, planet price tables, cargo management |
| `engine/ships_log.py` | ~266 | 17 milestones, 7 titles, CP rewards, log tracking |
| `engine/space_anomalies.py` | ~325 | 7 anomaly types, scanning, salvage, spawn ticks |
| `engine/npc_space_crew.py` | ~480 | NPC crew station assignment, skill rolls |
| `engine/npc_crew.py` | ~440 | NPC hiring/firing, wage deduction |
| `engine/skill_checks.py` | ~590 | Bargain, repair, coordinate resolvers |
| `data/starships.yaml` | ~400 | 19 ship templates with stats and weapons |
| `data/schematics.yaml` | ~260 | 7 ship component schematics |

**Total space system:** ~11,000+ lines of dedicated code across 11 files, plus shared dependencies.

---

*End of Guide #5 — Space Systems*
*Next: Guide #6 — Economy (Trading, Missions, Bounties, Smuggling)*

