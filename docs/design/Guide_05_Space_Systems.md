# SW_MUSH Detailed Systems Guide #5
# Space Systems

**SW_MUSH — Star Wars D6 Revised & Expanded**
**BTGlass80 — April 2026**
**Guide Version 1.0**

---

## How to Read This Guide

Space is the largest subsystem in the game — 49+ commands across ~5,184 lines of parser code plus ~2,700 lines of engine code across five engine files. This guide covers the full scope: galaxy structure, navigation, crew stations, space combat, trading, anomalies, ship customization, and progression.

---

## 1. The Galaxy Map

### Player Rules

The galaxy consists of **16 space zones** connected by **3 hyperspace lanes**, linking **4 planets**:

```
corellian_trade_spine ──── corellia_deep_space ── corellia_orbit ── corellia_dock
        │
outer_rim_lane_1 ──────── tatooine_deep_space ── tatooine_orbit ── tatooine_dock
        │
outer_rim_lane_2 ──────── nar_shaddaa_deep_space ── nar_shaddaa_orbit ── nar_shaddaa_dock
        │
outer_rim_lane_3 ──────── kessel_approach [HAZARD] ── kessel_orbit ── kessel_dock
```

Each planet has a chain: **dock → orbit → deep space → hyperspace lane**. The lanes connect the systems together.

| Planet | Docking Zone | Notable Features |
|--------|-------------|-----------------|
| **Tatooine** | Mos Eisley Docking Bay | Game hub, most NPCs and services |
| **Nar Shaddaa** | Docking Platform | Criminal underworld, smuggling hub |
| **Kessel** | Mining Station | Spice trade, dangerous deep mines |
| **Corellia** | Coronet Starport | CEC shipyards, legal commerce hub |

**Zone types** determine what happens there:
- **Dock** — Landing and launching. Safe harbor (secured security).
- **Orbit** — Transition between ground and space. Contested security.
- **Deep Space** — Open void. NPC traffic spawns here. Anomalies appear. Lawless security.
- **Hyperspace Lane** — Major shipping routes. Contested security.

### 🔧 Developer Internals

**File:** `engine/npc_space_traffic.py` — `ZONES` dict defines the complete zone graph with adjacency, zone types, planet keys, hazard flags, and environment strings. Zone IDs are integers; zone keys are strings.

**Room indexing:** Rooms are indexed by planet blocks (0–39 Tatooine, 40–54 Nar Shaddaa, 55–64 Kessel, 65–76 Corellia). `LandCommand` is planet-aware via the space zone's `.planet` field.

---

## 2. Ships and Ship Templates

### Player Rules

19 ship templates are defined, from light freighters to capital ships:

**Light Freighters:**

| Ship | Hull | Shields | Speed | Maneuver | Weapons | Cargo | Hyperdrive | Cost |
|------|------|---------|-------|----------|---------|-------|------------|------|
| YT-1300 | 4D | 1D | 4 | 1D | 1 Laser Cannon (turret, 4D) | 100t | x2 | 100K |
| Ghtroc 720 | 3D+1 | 1D | 3 | 1D | 1 Laser Cannon (front, 3D) | 135t | x2 | 98K |
| YT-2400 | 4D+1 | 2D | 4 | 1D+1 | 2 Laser Cannons (turret, 5D) | 150t | x2 | 130K |

**Starfighters:**

| Ship | Hull | Shields | Speed | Maneuver | Weapons | Hyperdrive |
|------|------|---------|-------|----------|---------|------------|
| X-Wing | 4D | 1D | 8 | 3D | 4 Laser Cannons (front, 6D) + Torpedoes | x1 |
| A-Wing | 3D+2 | 1D | 12 | 4D | 2 Laser Cannons (front, 5D) | x1 |
| Y-Wing | 5D | 1D+1 | 7 | 1D | 2 Laser Cannons + Ion Cannon + Torpedoes | x1 |
| B-Wing | 6D | 2D+2 | 6 | 1D+1 | 3 Laser/Ion Cannons + Torpedoes | x2 |
| TIE Fighter | 2D | 0D | 9 | 2D | 2 Laser Cannons (front, 5D) | None |
| TIE Interceptor | 3D | 0D | 11 | 3D+1 | 4 Laser Cannons (front, 6D) | None |
| TIE Bomber | 4D | 0D | 6 | 1D | 2 Laser Cannons + Ordnance | None |
| Firespray | 4D+2 | 2D | 7 | 2D | Blaster Cannon + Ion + Tractor | x1 |

**Capital Ships:** Corellian Corvette, Nebulon-B Frigate, Imperial Star Destroyer — all at capital scale (+6D difference from starfighters).

Ships have **mod slots** (typically 3–7) for installing crafted components and a **reactor_power** budget for the power allocation system.

### 🔧 Developer Internals

**File:** `data/starships.yaml` (~400 lines, 19 templates including aliases). Each template defines: `name`, `nickname`, `scale`, `hull`, `shields`, `speed`, `maneuverability`, `crew`, `passengers`, `cargo`, `consumables`, `hyperdrive`, `hyperdrive_backup`, `cost`, `mod_slots`, `reactor_power`, and `weapons[]` (each with `name`, `fire_arc`, `damage`, `fire_control`, `skill`).

**Alias pattern:** Some templates have two keys (e.g., `yt_1300` and `yt1300`) because different code paths use different naming conventions. Both point to identical stats.

**`get_effective_stats(ship)`:** Template stats are never permanently modified. Installed mods are stored in the ship's systems JSON, and effective stats are computed at read-time by adding mod bonuses to template base values. This is a key architecture pattern — all stat queries go through this function.

---

## 3. Crew Stations

### Player Rules

Ships operate with **seven crew stations**. On a solo flight, the pilot handles everything. On a crewed ship, dedicated operators at each station use their own skills:

| Station | Skill | What It Does | Key Commands |
|---------|-------|-------------|-------------|
| **Pilot** | Space Transports / Starfighter Piloting | Flies the ship, maneuvers, docks/launches | `course`, `close`, `flee`, `evade`, `tail` |
| **Copilot** | Space Transports | Assists pilot (+1D via Coordinate) | `assist` |
| **Gunner** | Starship Gunnery | Fires weapons, manages lock-on | `fire`, `lockon` |
| **Engineer** | ST Repair / Starfighter Repair | Damage control, power allocation, shields | `damcon`, `power`, `shields` |
| **Navigator** | Astrogation | Plots hyperspace courses | `hyperspace` |
| **Commander** | Command | Tactical orders that buff the crew | `coordinate`, `order` |
| **Sensors** | Sensors | Scans ships, anomalies, threats (+2D scan bonus) | `scan`, `deepscan` |

**NPC crew** can be hired to fill stations. Wages range from 30–1,000 credits every 4 hours depending on skill level. Commands: `hire <npc>`, `fire <npc>`, `assign <npc> <station>`.

**Taking a station:** `pilot`, `gunner`, `engineer`, `navigator`, `commander`, `sensors`, `copilot`. `vacate` to leave your station.

### 🔧 Developer Internals

**File:** `parser/space_commands.py` — Station commands (`PilotCommand`, `GunnerCommand`, etc.) each set the player's station in the ship's crew tracking. `VacateCommand` clears it. `AssistCommand` implements copilot's +1D bonus.

**File:** `engine/npc_crew.py` / `engine/npc_space_crew.py` — NPC crew management, wage deduction (4-hour tick), station assignment, skill dice used for rolls.

---

## 4. Navigation

### Player Rules

**Sublight navigation** — moving between adjacent zones:
```
course                    — Show current zone and adjacent zones
course <zone>             — Set course for adjacent zone
course cancel             — Cancel transit
```

Transit times: Dock ↔ Orbit (15s), Orbit ↔ Deep Space (20s), Deep Space ↔ Lane (25s). During transit, your ship is removed from the combat grid — you can't fire or be fired upon.

**Hyperspace travel** — jumping between star systems:
```
hyperspace                — List available destinations
hyperspace <destination>  — Jump to a destination
```

1. Navigator (or pilot) rolls Astrogation vs. Moderate difficulty
2. Success → enter hyperspace. Travel time = base time × hyperdrive multiplier
3. Failure → misjump (random zone). Critical failure → misjump + potential damage
4. Some ships have no hyperdrive (TIE Fighters) — they cannot jump

**Docking:**
```
land                      — Dock at a planet (must be in orbit/dock zone)
launch                    — Leave dock and enter orbit
```

### 🔧 Developer Internals

**`CourseCommand`** — Pilot-only. Checks zone adjacency in the zone graph, sets transit state in ship systems JSON, tick-based arrival. Piloting check on arrival determines how cleanly you enter the zone.

**`HyperspaceCommand`** — Travel time formula based on lane distance × hyperdrive multiplier. Transit state tracked in systems JSON. Tick hook checks arrival. `HYPERSPACE_DEST_TO_ZONE` mapping resolves destination names to zone keys.

**`LandCommand`** — Planet-aware via space zone's `.planet` field. Finds the appropriate docking bay room for the planet via `PLANET_BAY_SEARCH`. Triggers `auto_build_if_needed()` for dynamically-built rooms.

---

## 5. Space Combat

### Player Rules

Space combat uses the same D6 framework as ground combat but at ship scale with additional mechanics:

**Firing:** `fire <target>` — The gunner rolls Starship Gunnery + Fire Control vs. the target's piloting maneuverability. Range adds difficulty (Close +0, Short +5, Medium +10, Long +15, Extreme +25).

**Fire arcs:** Weapons have fire arcs (front, rear, turret). Turret weapons fire in all directions; front-only weapons can't hit targets behind you.

**Maneuvering:** Opposed piloting rolls to change the tactical situation:
- `close <target>` — Reduce range by one band
- `flee` — Increase range (escape attempt)
- `tail <target>` — Get behind target (rear position — they can't fire back-arc weapons at you)
- `outmaneuver <target>` — Force target to lose position advantage
- `evade` — Evasive maneuvers to break tail locks
- `jink` / `barrelroll` / `loop` / `slip` — Specialized maneuvers

**Speed advantage:** Faster ships get +1D per point of speed difference on piloting rolls.

**Targeting lock-on:** `lockon <target>` builds up a targeting bonus (+1D per round, max +3D). Consumed when you fire. Evasive maneuvers by the target clear all lock-ons.

**Shields:** `shields <front|rear|balanced>` — The engineer redistributes shield dice between arcs.

**Damage control:** `damcon <system>` — The engineer attempts to repair damaged systems mid-combat. Uses Technical + repair skill vs. difficulty per system type. Systems track three states: working → damaged → destroyed.

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

---

## 6. Power Allocation

### Player Rules

Each ship has a **reactor power** budget (e.g., 10 for a YT-1300). Active systems draw power:

```
power                     — Show current allocation
power engines 4           — Allocate 4 power to engines
power shields 3           — Allocate 3 power to shields
power weapons 2           — Allocate 2 power to weapons
power silent              — Silent running (minimize emissions)
```

Over-allocating to one system means under-powering others. An engineer who dumps everything into weapons leaves shields paper-thin. This creates meaningful tactical choices — FTL-inspired power management in a Star Wars setting.

**Silent running** reduces sensor signature but limits all systems.

### 🔧 Developer Internals

Power allocation is transient (stored in systems JSON). Default allocation on boot. Engineer station required to change. Each system has a power cost and a performance multiplier based on allocated power vs. required power.

---

## 7. Captain's Orders

### Player Rules

The Commander station can issue tactical orders that apply ship-wide bonuses:

```
order                     — Show available orders
order <order_name>        — Issue an order (Commander skill check)
```

Orders are resolved via a Command skill check. Success applies a modifier to all crew rolls for the round. Critical success doubles the bonus. Only one order can be active at a time.

### 🔧 Developer Internals

8 tactical order types defined in the space expansion addendum. Commander issues via `OrderCommand`, resolved through `resolve_coordinate_check()` in `skill_checks.py`. Orders stored in ship state and applied as modifiers during crew skill rolls.

---

## 8. Cargo Trading

### Player Rules

Buy-low-sell-high speculative trading between planets. 8 trade goods with planet-specific pricing:

| Trade Good | Base Price | Source (50%) | Demand (200%) |
|-----------|-----------|-------------|---------------|
| Raw Ore | 100 cr/ton | Tatooine, Kessel | Corellia |
| Foodstuffs | 80 cr/ton | Corellia | Kessel, Nar Shaddaa |
| Manufactured Parts | 200 cr/ton | Corellia | Tatooine, Nar Shaddaa |
| Medical Supplies | 150 cr/ton | Corellia | Kessel, Tatooine |
| Spice (Legal) | 300 cr/ton | Kessel | Nar Shaddaa |
| Electronics | 250 cr/ton | Corellia | Tatooine |
| Luxury Goods | 400 cr/ton | Corellia, Nar Shaddaa | Tatooine |
| Weapons (Licensed) | 350 cr/ton | Corellia | Nar Shaddaa |

**Commands:**
```
market                    — Show available goods and prices at current planet
buy <good> <quantity>     — Purchase cargo (Bargain check modifies price)
sell <good>               — Sell cargo at current planet
```

Buying at a source planet (50% price) and selling at a demand planet (200% price) yields a 4x markup. Bargain skill checks can further modify the price by ±10%.

### 🔧 Developer Internals

**File:** `engine/trading.py` (~335 lines):
- `TradeGood` dataclass: `key`, `name`, `base_price`, `description`, `source[]`, `demand[]`, `tons_per_unit`
- `TRADE_GOODS` dict: 8 goods with planet-specific source/demand lists
- Price tiers: `PRICE_SOURCE = 0.50`, `PRICE_NORMAL = 1.00`, `PRICE_DEMAND = 2.00`
- Cargo stored in ship's `cargo` JSON column as `[{"good": "raw_ore", "quantity": 50, "purchase_price": 50}, ...]`

Bargain checks route through `skill_checks.py::resolve_bargain_check()`.

---

## 9. Transponder Codes and Sensor Countermeasures

### Player Rules

Ships carry transponder codes that identify them. Players can install countermeasures:

- **False transponder** — Disguise your ship's identity
- **Sensor mask** — Reduce sensor detectability
- **Comm jammer** — Block communications in your zone

Imperial customs patrols check transponders and levy fines for irregularities per WEG smuggling rules (sourced from Platt's Smugglers Guide WEG40141 and Pirates & Privateers WEG40143).

### 🔧 Developer Internals

`TransponderCommand` in `parser/space_commands.py`. Countermeasure items crafted via the crafting system (Sensor Mask and Comm Jammer schematics in `data/schematics.yaml`).

---

## 10. Space Anomalies and Salvage

### Player Rules

Seven types of anomalies spawn randomly in space zones:

| Anomaly | Scans Needed | Description |
|---------|-------------|-------------|
| Derelict Ship | 3 | Unpowered vessel adrift. Salvageable components. |
| Distress Signal | 2 | Emergency beacon. Could be genuine or an ambush. |
| Hidden Cache | 3 | Armored container — requires close approach + security bypass. |
| Pirate Nest | 2 | 2–3 hostiles waiting in ambush. Salvage on victory. |
| Asteroid Mineral Vein | 2 | High-grade ore. Technical check to extract resources. |
| Imperial Dead Drop | 4 | Encrypted intelligence. Difficult slicing check; failure triggers patrol. |
| Mynock Colony | 1 | Hull parasites. 1 system damage on approach; Easy piloting to detach. |

**Scanning:** Use `deepscan` to progressively reveal anomaly details. Each scan resolves one level of description (vague → partial → full). Once fully scanned, some can be investigated via `course anomaly <id>`.

**Anomaly state is transient** — server restarts wipe them, and they respawn on timers. This is intentional.

### 🔧 Developer Internals

**File:** `engine/space_anomalies.py` (~325 lines):
- `ANOMALY_TYPES` list: 7 types with spawn weights, scan thresholds, and three description tiers (vague/partial/full)
- Module-level state dict (no DB) — `_anomalies: dict[str, list[Anomaly]]` keyed by zone
- `spawn_anomalies_for_zone()` — Called from tick (every 300 ticks)
- `get_anomalies_for_zone()` / `get_scan_result_text()` — Used by `DeepScanCommand`
- `tick_anomaly_expiry()` — Prune stale entries

---

## 11. Ship Customization and Modifications

### Player Rules

Ships have **mod slots** (varies by template, typically 3–7). Crafted ship components can be installed:

| Component | Stat Boosted | Craft Skill | Resources |
|-----------|-------------|-------------|-----------|
| Engine Booster | Speed | Space Transports Repair | Metal, Energy, Composite |
| Shield Generator Mk2 | Shields | Starship Repair | Metal, Energy, Rare |
| Armor Plating | Hull | Armor Repair | Metal, Composite |
| Sensor Suite Enhanced | Sensors | Sensors Repair | Energy, Rare |
| Maneuvering Thrusters | Maneuverability | Space Transports Repair | Metal, Energy |
| Weapon Upgrade FC | Fire Control | Starship Weapons Repair | Metal, Energy, Rare |
| Hyperdrive Tuning | Hyperdrive | Space Transports Repair | Energy, Composite, Rare |

Installation requires docking at a planet and passing a skill check. Stats are computed at read-time via `get_effective_stats()` — template stats are never permanently modified.

### 🔧 Developer Internals

Mods stored in ship's systems JSON. `get_effective_stats()` is the single entry point for all stat queries — adds mod bonuses to template base values. 7 component schematics defined in `data/schematics.yaml`.

---

## 12. Ship's Log and Titles

### Player Rules

The ship's log tracks 17 milestones across categories: zones visited, ships scanned, anomalies resolved, planets landed, pirate kills, smuggling runs, and trade runs. Reaching thresholds awards CP ticks and earns titles:

| Title | Requirement | CP Reward |
|-------|------------|-----------|
| Explorer | Visit all 16 zones | 50 CP |
| Spotter | Scan all 19 ship types | 30 CP |
| Archaeologist | Resolve all 7 anomaly types | 30 CP |
| Galactic Traveler | Land on all 4 planets | 20 CP |
| Pirate Hunter | 100 pirate kills | 50 CP |
| Ace Smuggler | 50 smuggling runs | 50 CP |
| Merchant Prince | 50 profitable trade runs | 30 CP |

Titles display on your character sheet and in the `who` list.

### 🔧 Developer Internals

**File:** `engine/ships_log.py` (~266 lines):
- `DEFAULT_LOG` dict: 11 tracking categories
- `MILESTONES` list: 17 milestone definitions with `category`, `threshold`, `cp` reward, optional `title`, and `msg`
- Stored in character attributes JSON under `"ships_log"` key
- `check_milestones()` compares current log values against thresholds, awards CP via existing `CPEngine` tick system

---

## 13. NPC Space Traffic

### Player Rules

NPC ships travel the spacelanes — freighters hauling cargo, Imperial patrols checking transponders, pirate raiders stalking prey. You'll encounter them as you navigate between zones. Pirates will tail and attack player ships in lawless zones. Imperial patrols hail and scan in contested zones.

### 🔧 Developer Internals

**File:** `engine/npc_space_traffic.py` (~1,900 lines) — The largest single engine file. Manages NPC ship spawning, zone-to-zone transit, patrol encounters, pirate attacks, customs inspections, and per-zone ship caps to prevent spam.

---

## 14. Web Client Space HUD

### Player Rules

The web client provides a rich space interface:
- **Zone Map SVG** — Visual map with your current location highlighted
- **Tactical Radar SVG** — Real-time display of ships in your zone
- **Ship Status Schematic** — SVG showing system states
- **Power Allocation Bar** — Visual distribution of reactor power
- **Captain's Order Badge** — Active tactical order display
- **Station-Aware Quick Buttons** — Context buttons change based on your crew station

### 🔧 Developer Internals

`build_space_state()` and `broadcast_space_state()` helpers in `parser/space_commands.py` serialize the complete space state for WebSocket delivery. Send points wired into LaunchCommand, LandCommand, FireCommand, ShieldsCommand, hyperspace/sublight arrival ticks.

---

## 15. Space Commands Quick Reference

| Category | Commands |
|----------|---------|
| **Ship Management** | `ships`, `shipinfo`, `myships`, `board`, `disembark`, `pay` |
| **Crew Stations** | `pilot`, `copilot`, `gunner`, `engineer`, `navigator`, `commander`, `sensors`, `vacate` |
| **Navigation** | `course`, `hyperspace`, `land`, `launch` |
| **Combat** | `fire`, `lockon`, `close`, `flee`, `tail`, `outmaneuver`, `evade`, `jink`, `barrelroll`, `loop`, `slip` |
| **Ship Operations** | `scan`, `deepscan`, `shields`, `damcon`, `power`, `coordinate`, `assist`, `order` |
| **Economy** | `market`, `buy`, `sell`, `salvage`, `hail`, `comms`, `transponder` |
| **Admin** | `spawn` (staff) |

---

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
