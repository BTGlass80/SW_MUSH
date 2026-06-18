---
category: galaxy
order: 2
summary: "Pilot, navigate, dock, and fight in space. Hyperspace routes, ship combat, and starship roles."
tags: ["space", "ship", "starship", "pilot", "hyperspace", "navigation", "freighter"]
---

# Space Systems

**SW_MUSH — Star Wars D6 Revised & Expanded**
**BTGlass80 — April 2026**
**Guide Version 1.0**

---

## How to Read This Guide

Space is the largest subsystem in the game — 49+ commands across ~5,184 lines of parser code plus ~2,700 lines of engine code across five engine files. This guide covers the full scope: galaxy structure, navigation, crew stations, space combat, trading, anomalies, ship customization, and progression.

---

## 1. The Galaxy Map

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

---

## 2. Ships and Ship Templates

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
| ARC-170 Starfighter | 4D | 1D | 8 | 3D | 4 Laser Cannons (front, 6D) + Torpedoes | x1 |
| Eta-2 Actis Interceptor | 3D+2 | 1D | 12 | 4D | 2 Laser Cannons (front, 5D) | x1 |
| BTL-B Y-Wing | 5D | 1D+1 | 7 | 1D | 2 Laser Cannons + Ion Cannon + Torpedoes | x1 |
| B-Wing | 6D | 2D+2 | 6 | 1D+1 | 3 Laser/Ion Cannons + Torpedoes | x2 |
| Vulture Droid Starfighter | 2D | 0D | 9 | 2D | 2 Laser Cannons (front, 5D) | None |
| Tri-Fighter | 3D | 0D | 11 | 3D+1 | 4 Laser Cannons (front, 6D) | None |
| Hyena-class Bomber | 4D | 0D | 6 | 1D | 2 Laser Cannons + Ordnance | None |
| Firespray | 4D+2 | 2D | 7 | 2D | Blaster Cannon + Ion + Tractor | x1 |

**Capital Ships:** Corellian Corvette, Nebulon-B Frigate, Venator-class Star Destroyer — all at capital scale (+6D difference from starfighters).

Ships have **mod slots** (typically 3–7) for installing crafted components and a **reactor_power** budget for the power allocation system.

---

## 3. Crew Stations

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

---

## 4. Navigation

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
4. Some ships have no hyperdrive (Vulture Droid Starfighters) — they cannot jump

**Docking:**
```
land                      — Dock at a planet (must be in orbit/dock zone)
launch                    — Leave dock and enter orbit
```

---

## 5. Space Combat

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

---

## 6. Power Allocation

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

---

## 7. Captain's Orders

The Commander station can issue tactical orders that apply ship-wide bonuses:

```
order                     — Show available orders
order <order_name>        — Issue an order (Commander skill check)
```

Orders are resolved via a Command skill check. Success applies a modifier to all crew rolls for the round. Critical success doubles the bonus. Only one order can be active at a time.

---

## 8. Cargo Trading

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

---

## 9. Transponder Codes and Sensor Countermeasures

Ships carry transponder codes that identify them. Players can install countermeasures:

- **False transponder** — Disguise your ship's identity
- **Sensor mask** — Reduce sensor detectability
- **Comm jammer** — Block communications in your zone

Republic customs patrols check transponders and levy fines for irregularities per WEG smuggling rules (sourced from Platt's Smugglers Guide WEG40141 and Pirates & Privateers WEG40143).

---

## 10. Space Anomalies and Salvage

Seven types of anomalies spawn randomly in space zones:

| Anomaly | Scans Needed | Description |
|---------|-------------|-------------|
| Derelict Ship | 3 | Unpowered vessel adrift. Salvageable components. |
| Distress Signal | 2 | Emergency beacon. Could be genuine or an ambush. |
| Hidden Cache | 3 | Armored container — requires close approach + security bypass. |
| Pirate Nest | 2 | 2–3 hostiles waiting in ambush. Salvage on victory. |
| Asteroid Mineral Vein | 2 | High-grade ore. Technical check to extract resources. |
| Republic Dead Drop | 4 | Encrypted intelligence. Difficult slicing check; failure triggers patrol. |
| Mynock Colony | 1 | Hull parasites. 1 system damage on approach; Easy piloting to detach. |

**Scanning:** Use `deepscan` to progressively reveal anomaly details. Each scan resolves one level of description (vague → partial → full). Once fully scanned, some can be investigated via `course anomaly <id>`.

**Anomaly state is transient** — server restarts wipe them, and they respawn on timers. This is intentional.

---

## 11. Ship Customization and Modifications

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

### Wildspace Ship Mods

Three additional mod types unlock Wildspace resource operations (`mine`, `salvage`, `refine` commands). All are crafted by **Venn Kator** (Space Transports Repair).

| Mod | Effect | Craft Diff | Resources | Rep Gate |
|-----|--------|-----------|-----------|---------|
| **Mining Laser Mk1** | +2D mining check; -25% mine cooldown | 16 | 12 metal + 4 energy | None |
| **Mining Laser Mk2** | +3D mining check; -40% cooldown; deep mining on critical | 20 | 24 metal + 8 energy + 2 rare | Hutt Cartel 25+ |
| **Reinforced Salvage Arm Mk1** | +2D salvage check; +1 component per run | 16 | 8 metal + 4 composite | None |
| **Reinforced Salvage Arm Mk2** | +3D salvage check; +2 components per run; intact extraction | 20 | 16 metal + 8 composite + 2 rare | Republic 25+ |
| **Onboard Refinery** | Enables `refine` command mid-flight (raw → refined resources) | 18 | 10 metal + 6 energy + 4 composite | None |

Mining Laser Mk2 enables **deep mining** — a critical success on the `mine` roll yields a bonus rare resource draw that Mk1 cannot reach. Salvage Arm Mk2 adds **intact extraction** — a chance to recover a complete undamaged component from a derelict. Mk2 mods require replacing the Mk1 first (one mod slot per type). Only one Mining Laser and one Salvage Arm can be installed simultaneously; the Onboard Refinery uses its own slot.

---

## 12. Ship's Log and Titles

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

Titles display on your character sheet and in the `+who` list.

---

## 13. NPC Space Traffic

NPC ships travel the spacelanes — freighters hauling cargo, Republic clone patrol checking transponders, pirate raiders stalking prey. You'll encounter them as you navigate between zones. Pirates will tail and attack player ships in lawless zones. Republic clone patrol hail and scan in contested zones.

---

## 14. Web Client Space HUD

The web client provides a rich space interface:
- **Zone Map SVG** — Visual map with your current location highlighted
- **Tactical Radar SVG** — Real-time display of ships in your zone
- **Ship Status Schematic** — SVG showing system states
- **Power Allocation Bar** — Visual distribution of reactor power
- **Captain's Order Badge** — Active tactical order display
- **Station-Aware Quick Buttons** — Context buttons change based on your crew station

---

## 15. Space Commands Quick Reference

| Category | Commands |
|----------|---------|
| **Ship Management** | `+ship`, `+ship/list`, `+ship/info`, `+ship/mine`, `board`, `disembark`, `pay` |
| **Crew Stations** | `pilot`, `copilot`, `gunner`, `engineer`, `navigator`, `commander`, `sensors`, `vacate` |
| **Navigation** | `course`, `hyperspace`, `land`, `launch` |
| **Combat** | `fire`, `lockon`, `close`, `flee`, `tail`, `outmaneuver`, `evade`, `jink`, `barrelroll`, `loop`, `slip` |
| **Ship Operations** | `scan`, `deepscan`, `shields`, `damcon`, `power`, `coordinate`, `assist`, `order` |
| **Economy** | `market`, `buy`, `sell`, `salvage`, `hail`, `comms`, `transponder` |
| **Admin** | `spawn` (staff) |

---

