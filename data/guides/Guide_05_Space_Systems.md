---
category: galaxy
order: 2
summary: "Pilot, navigate, dock, and fight in space. Hyperspace routes, ship combat, trading, and starship roles in the Clone Wars galaxy."
tags: ["space", "ship", "starship", "pilot", "hyperspace", "navigation", "freighter"]
---

# Space Systems

**Parsec — WEG D6 Revised & Expanded**
**BTGlass80 — April 2026**
**Guide Version 1.1**

---

## How to Read This Guide

Space is the largest subsystem in the game. This guide covers the full scope:
galaxy structure, navigation, crew stations, space combat, trading, anomalies,
ship customization, and progression. Every command, stat, and price below is
checked against the live engine — where the game and an older draft disagreed,
the game wins.

Solo or crewed, the loop is the same: launch, fly a lane, find trouble or
profit, and bring the ship home in one piece.

---

## 1. The Galaxy Map

The Clone Wars galaxy is **six planets**, each reached through a chain of
**dock → orbit → deep space** zones, stitched together by **six hyperspace
lanes** and ringed by **four Wildspace salvage zones**. Twenty-eight zones in
all.

```
                         Kuat ── Kuat Deep Space ─┐
                                                  │  Hydian Way
        Kamino ── Kamino Deep ── Kamino Approach ─┤
                                                  │
                    Coruscant ── Coruscant Deep ──┴── Perlemian ── (Outer Rim Sieges)
                            │              │
                       Hydian Way     Corellian Run
                                           │
        Tatooine ── Tatooine Deep ─────────┴── Triellus ── Geonosis Deep ── Geonosis
                        │                          │
                   Jundland Drift            Hutt Space Corridor
                                                   │
        Nar Shaddaa ── Nar Shaddaa Deep ───────────┴── Smuggler's Run Periphery
```

Every planet has the same three-zone chain — **dock → orbit → deep space** —
and each deep-space zone opens onto one or more hyperspace lanes.

| Planet | Authority | Docking Zone | Character |
|--------|-----------|--------------|-----------|
| **Tatooine** | Hutt | Mos Eisley Approach | Game hub. Most NPCs, services, the cantina. |
| **Nar Shaddaa** | Hutt | Nar Shaddaa Landing Platform | The Smuggler's Moon — criminal underworld. |
| **Coruscant** | Republic | Coruscant Westport Arrivals | Galactic capital; three great lanes converge here. |
| **Kuat** | Republic | Kuat Spaceport Approach | KDY shipyards; the Republic's industrial heart. |
| **Kamino** | Republic | Tipoca City Landing Platform | Restricted clone facility, reached only via a hazard lane. |
| **Geonosis** | CIS | Stalgasin Hive Landing Pads | Separatist industrial front. Republic ships are interdicted. |

**Hyperspace lanes** (six): the Perlemian Trade Route, the Hydian Way, the
Corellian Run, the Triellus Trade Route, the Hutt Space Corridor, and the
classified **Kamino Approach** — the only navigation-hazard lane in the graph
(the Rishi Maze's gravity shadow imposes an astrogation penalty).

**Wildspace zones** (four): designated salvage/grind pockets branching off
civilized deep space — **Geonosis Front** and **Outer Rim Sieges Drift** (the
Sieges theater) and **Jundland Drift** and **Smuggler's Run Periphery** (the
Hutt Frontier theater). They carry no RP hooks and no friendly NPC traffic —
just caches, hazards, and whatever else is out there hunting them. See §10.

**Zone authority** flags who runs the space — **Hutt**, **Republic**, **CIS**,
or **contested**. Authority colors the flavor (whose patrols you meet, who
interdicts you); the **security tier** that governs combat is set by zone
**type**:

- **Dock** — Landing and launching. **Secured**: no weapons fire.
- **Orbit** — Transition between ground and space. **Contested**.
- **Deep Space** — Open void. NPC traffic and anomalies spawn here. **Lawless** (open PvP).
- **Hyperspace Lane** — Shipping routes. **Contested**.

---

## 2. Ships and Ship Templates

The Clone Wars registry carries **21 distinct hulls** — a base catalog of
era-agnostic ships (the YT freighters, the Z-95, the Firespray, the Corellian
Corvette) plus a Clone Wars overlay of Republic and Separatist vessels.
Post-Clone-Wars hulls are excluded from this era: they will not register, spawn,
or appear in the catalog.

Stats below are the live template values. **Hyperdrive** is the multiplier
(lower is faster; x1 is twice as fast as x2); **None** means no internal drive —
the ship is carrier-deployed or rides an external booster.

### Light Freighters & Transports

| Ship | Hull | Shields | Speed | Maneuver | Weapons | Cargo | Hyperdrive | Cost |
|------|------|---------|-------|----------|---------|-------|------------|------|
| YT-1300 Transport | 4D | 1D | 4 | 1D | Laser Cannon (turret, 4D) | 100t | x2 | 100,000 |
| Ghtroc 720 Freighter | 4D | 1D | 3 | 1D | — | 135t | x2 | 98,500 |
| YT-2400 Transport | 4D+2 | 2D | 5 | 1D+2 | 2 Laser Cannons (turret, 4D) | 150t | x2 | 130,000 |
| Sheathipede Shuttle | 2D+2 | 1D | 4 | 1D+2 | 2 Laser Cannons (front, 3D) | 100t | x2* | 50,000 |
| Consular-class Cruiser | 3D+1 | 1D+2 | 5 | 2D | 2 Double Turbolasers (turret, 4D) | 1,500t | x2 | 1,500,000 |

\* The Sheathipede has no fixed hyperdrive — the x2 rating requires its booster sled.

### Republic Starfighters

| Ship | Hull | Shields | Speed | Maneuver | Weapons | Hyperdrive |
|------|------|---------|-------|----------|---------|------------|
| ARC-170 Starfighter | 4D | 1D+2 | 7 | 2D | 2 Laser (front, 5D) + 2 rear (3D) + 6 Proton Torpedoes (9D) | x1.5 |
| V-19 Torrent | 2D+2 | 1D | 11 | 3D+1 | 2 Laser (front, 4D) + Concussion Missiles (7D) | None |
| Eta-2 Actis (Jedi Interceptor) | 2D+1 | 0D | 13 | 4D | 2 Laser (front, 4D) + 2 Ion Cannons (3D) | None* |
| LAAT/i Gunship | 3D+2 | 1D | 6 | 2D | Mass-driver + AP turrets + Missiles + Rockets | None |
| BTL-B Y-Wing | 4D | 1D+2 | 7 | 2D | 2 Laser (front, 5D) + 2 Proton Torpedoes (9D) + Ion (4D) | x1 |

\* The Eta-2 jumps only with an external hyperdrive booster ring (a separate vehicle).

### Independent & Patrol Craft

| Ship | Hull | Shields | Speed | Maneuver | Weapons | Hyperdrive |
|------|------|---------|-------|----------|---------|------------|
| Z-95 Headhunter | 3D | 1D | 7 | 1D | 2 Triple Blasters (front, 3D) + Concussion Missiles (7D) | None |
| Firespray Patrol Craft | 5D | 2D | 7 | 1D | Twin Blaster (5D) + Concussion (7D) + Tractor Beam | x2 |

### CIS Droid Fighters (drone — no pilot)

| Ship | Hull | Shields | Speed | Maneuver | Weapons | Hyperdrive |
|------|------|---------|-------|----------|---------|------------|
| Vulture Droid | 2D | 0D | 9 | 3D | 4 Blasters (front, 3D+2) + Energy Torpedoes (6D) | None |
| Hyena-class Bomber | 2D+2 | 0D | 6 | 2D | Lasers + 6 Proton Bombs (9D) + Concussion Missiles (7D) | None |
| Droid Tri-Fighter | 2D+1 | 0D | 10 | 3D+2 | 4 Laser Cannons + Buzz-Droid Missiles | None |

### Capital Ships

Capital ships fight at **capital scale** (+6D against starfighter-scale targets,
and vice versa). The military capitals below are NPC fleet presence — they crew
in the thousands, carry no purchase price, and are scan/encounter targets, not
player purchases. The Corellian Corvette and Consular Cruiser are the
player-reachable end of the scale.

| Ship | Scale | Hull | Shields | Speed | Maneuver | Hyperdrive | Note |
|------|-------|------|---------|-------|----------|------------|------|
| Corellian Corvette (CR90) | capital | 4D | 2D | 6 | 2D | x2 | Purchasable (3.5M); fast blockade-runner. |
| Venator-class Star Destroyer | capital | 4D | 3D | 4 | 1D | x1 | Republic carrier/destroyer. NPC. |
| Acclamator-class Assault Ship | capital | 3D+2 | 2D+2 | 4 | 1D | x0.6 | Republic clone transport; atmosphere-capable. NPC. |
| Lucrehulk-class Battleship | capital | 5D | 4D | 2 | 0D | x2 | Trade Federation flagship; droid carrier. NPC. |
| Munificent-class Frigate | capital | 4D | 2D+2 | 4 | 1D | x1 | CIS long-range gunnery platform. NPC. |
| Recusant-class Light Destroyer | capital | 3D+2 | 2D | 4 | 1D | x1 | Mass-produced CIS destroyer; fights in formation. NPC. |

Ships have **mod slots** (typically 2–7) for installing crafted components and a
**reactor power** budget for the power-allocation system (§6). Browse the full
catalog in-game with `+ship/list` and any ship's specs with `+ship/info <name>`.

---

## 3. Crew Stations

Ships operate with **seven crew stations**. On a solo flight the pilot handles
everything. On a crewed ship, dedicated operators at each station use their own
skills:

| Station | Skill | What It Does | Key Commands |
|---------|-------|--------------|--------------|
| **Pilot** | Space Transports / Starfighter Piloting | Flies the ship, maneuvers, docks/launches | `course`, `close`, `flee`, `evade`, `tail` |
| **Copilot** | Space Transports | Assists pilot (+1D via Coordinate) | `assist` |
| **Gunner** | Starship Gunnery | Fires weapons, manages lock-on | `fire`, `lockon` |
| **Engineer** | ST Repair / Starfighter Repair | Damage control, power, shields | `damcon`, `power`, `shields`, `+ship/repair` |
| **Navigator** | Astrogation | Plots hyperspace courses | `hyperspace` |
| **Commander** | Command | Tactical orders that buff the crew | `coordinate`, `order` |
| **Sensors** | Sensors | Scans ships, anomalies, threats | `scan`, `deepscan` |

**Taking a station:** `pilot`, `copilot`, `gunner`, `engineer`, `navigator`,
`commander`, `sensors`. `vacate` leaves your station.

**NPC crew** can be hired to fill stations on a ship you own or are authorized to
fly. Commands: `hire <npc>`, `fire <npc>`, `assign <npc> <station>`, `pay`.

---

## 4. Navigation

**Sublight navigation** — moving between adjacent zones:
```
course                    — Show current zone and adjacent zones
course <zone>             — Set course for an adjacent zone
course cancel             — Cancel transit
```

During transit your ship is off the combat grid — you can't fire or be fired
upon. You can only move to a zone listed as *adjacent* to your current one;
crossing the galaxy means hopping the chain or jumping a lane.

**Hyperspace travel** — jumping along a lane to a distant system:
```
hyperspace                — List available destinations
hyperspace <destination>  — Jump to a destination
```

1. The navigator (or a solo pilot) rolls **Astrogation** vs. the route difficulty.
2. Success → enter hyperspace; travel time = base time × hyperdrive multiplier.
3. Failure → misjump (random zone). Critical failure → misjump plus possible damage.
4. Some hulls have no hyperdrive (droid fighters, the V-19, the Eta-2 without its
   ring) — they cannot jump and must be carried.

The **Kamino Approach** is the one lane with a standing navigation hazard: the
Rishi Maze imposes an astrogation penalty and a sensor penalty, and Republic
interdictors inspect every transit.

**Docking:**
```
land                      — Dock at a planet (from its orbit zone)
launch                    — Leave the dock and enter orbit
```

---

## 5. Space Combat

Space combat uses the same D6 framework as ground combat, at ship scale, with
extra positioning mechanics:

**Firing:** `fire <target>` — the gunner rolls Starship Gunnery + Fire Control
vs. the target's piloting/maneuverability. Range adds difficulty (Close +0,
Short +5, Medium +10, Long +15, Extreme +25).

**Fire arcs:** Weapons fire in an arc (front, rear, turret). Turret weapons hit
in all directions; front-only weapons can't reach a target behind you.

**Maneuvering** — opposed piloting rolls that change the tactical picture:
- `close <target>` — Reduce range by one band
- `flee` — Increase range (escape attempt)
- `tail <target>` — Get behind the target (rear position — they can't bring back-arc weapons to bear)
- `outmaneuver <target>` — Strip the target's position advantage
- `evade` — Evasive action to break tail locks (clears lock-ons against you)
- `jink` / `barrelroll` / `loop` / `slip` — Specialized maneuvers

**Speed advantage:** Faster ships gain +1D per point of speed difference on
piloting rolls — the reason a Vulture Droid or Eta-2 can dance around a freighter.

**Targeting lock-on:** `lockon <target>` builds a targeting bonus (+1D per round,
max +3D), consumed when you fire. Evasive maneuvers by the target clear all
lock-ons against it.

**Shields:** `shields <front|rear|balanced>` — the engineer redistributes shield
dice between arcs.

**Damage control:** `damcon <system>` — the engineer repairs damaged systems
mid-combat (Technical + repair vs. difficulty per system). Systems track
**working → damaged → destroyed**.

---

## 6. Power Allocation

Each ship has a **reactor power** budget (10 for a YT-1300, up to 36 for a
Lucrehulk). Active systems draw power:

```
power                     — Show current allocation
power engines 4           — Allocate 4 power to engines
power shields 3           — Allocate 3 power to shields
power weapons 2           — Allocate 2 power to weapons
power silent              — Silent running (minimize emissions)
```

Over-feeding one system starves the others. Dump everything into weapons and
your shields go paper-thin. This is FTL-style power management in a Star Wars
hull — meaningful tactical choices every round.

**Silent running** cuts your sensor signature but throttles every system.

---

## 7. Captain's Orders

The Commander station issues tactical orders that buff the whole crew:

```
order                     — Show available orders
order <order_name>        — Issue an order (Command skill check)
```

Orders resolve via a Command check; success applies a modifier to all crew rolls
for the round, and a critical success doubles it. Only one order can be active at
a time.

---

## 8. Cargo Trading

Buy-low-sell-high speculative trading between planets. **Eight trade goods**,
each cheap at its **source** worlds and dear at its **demand** worlds:

| Trade Good | Base Price | Source (70%) | Demand (140%) |
|-----------|-----------|-------------|---------------|
| Raw Ore | 100 cr/ton | Tatooine, Geonosis | Kuat, Coruscant |
| Foodstuffs | 80 cr/ton | Coruscant | Kamino, Tatooine, Geonosis |
| Manufactured Parts | 200 cr/ton | Kuat | Geonosis, Tatooine |
| Medical Supplies | 150 cr/ton | Kamino | Geonosis, Tatooine, Nar Shaddaa |
| Spice (Legal Grade) | 300 cr/ton | Nar Shaddaa | Coruscant |
| Electronics | 250 cr/ton | Geonosis, Kuat | Coruscant, Nar Shaddaa |
| Luxury Goods | 400 cr/ton | Nar Shaddaa | Coruscant, Tatooine |
| Weapons (Licensed) | 350 cr/ton | Nar Shaddaa | Geonosis, Tatooine |

**Commands:**
```
market                    — Show goods and prices at the current planet
buy <good> <quantity>     — Purchase cargo (Bargain check modifies price)
sell <good>               — Sell cargo at the current planet
```

Buying at a **source** world (70%) and selling into **demand** (140%) is roughly
a **2× turn**, before your Bargain check — which nudges the price up to ±10%
either way. Every world is both a source for something and a demand for
something else, so there's always a return cargo.

**Demand saturation:** selling repeatedly into the same world depresses its
price — about 0.5% per ton recently sold, capped at a 30% reduction. The first
trader to a demand world gets the best price; flood it and the margin thins. Spread
your runs, or let a market recover.

---

## 9. Transponder Codes and Sensor Countermeasures

Ships carry transponder codes that identify them. Players can install
countermeasures:

- **False transponder** — Disguise your ship's identity
- **Sensor mask** — Reduce sensor detectability
- **Comm jammer** — Block communications in your zone

Republic customs and Hutt cartel patrols check transponders and levy fines for
irregularities, per WEG smuggling rules (Platt's Smugglers Guide WEG40141,
Pirates & Privateers WEG40143).

---

## 10. Space Anomalies, Salvage, and Wildspace

**Seven anomaly types** spawn randomly in deep space, lanes, and orbits (never
at dock):

| Anomaly | Scans Needed | Description |
|---------|-------------|-------------|
| Derelict Ship | 3 | Unpowered vessel adrift. Salvageable components. |
| Distress Signal | 2 | Emergency beacon. Genuine — or an ambush. |
| Hidden Cache | 3 | Armored container; close approach + security bypass. |
| Pirate Nest | 2 | 2–3 hostiles waiting in ambush. Salvage on victory. |
| Asteroid Mineral Vein | 2 | High-grade ore. Technical check to extract. |
| Republic Dead Drop | 4 | Encrypted intel. Difficult slicing check; failure triggers a patrol. |
| Mynock Colony | 1 | Hull parasites — 1 system damage on approach; Easy piloting to detach. |

**Scanning:** `deepscan` progressively reveals an anomaly (vague → partial →
full), identifying what you've found. The wired payoff today is **salvage** —
once a Derelict Ship (or a combat wreck) is identified, `salvage` recovers
components from it. Richer per-type engagement (slicing a dead drop, bypassing a
cache, clearing a pirate nest) is on the roadmap, not yet live. Anomaly state is
transient — server restarts wipe the field and anomalies respawn on timers. This
is intentional.

**Wildspace grind:** the four Wildspace zones (§1) are dedicated salvage pockets.
With the right ship mods (§11) you can `mine` asteroid veins, `salvage`
derelicts, and `refine` raw resources in-flight. The two theaters — Sieges
(Geonosis Front, Outer Rim Sieges Drift) and Hutt Frontier (Jundland Drift,
Smuggler's Run Periphery) — pull from different cache content sets, carry light
asteroid hazards, and host no friendly traffic. Lawless space: bring a gun.

---

## 11. Ship Customization and Modifications

Ships have **mod slots** (2–7 by template). Crafted components install into a
slot and apply at read-time via `get_effective_stats()` — template stats are
never permanently overwritten. Install and manage mods with:

```
+ship/mods                          — Show installed modifications
+ship/install <component name>      — Install a crafted component
+ship/uninstall <slot#>             — Remove the mod in a slot
```

Standard stat-boosting mods (crafted, then installed at a slot):

| Component | Stat Boosted | Craft Skill |
|-----------|-------------|-------------|
| Engine Booster (Basic) | Speed | Space Transports Repair |
| Shield Generator Mk.II | Shields | Starship Repair |
| Durasteel Armor Plating | Hull | Armor Repair |
| Enhanced Sensor Suite | Sensors | Sensors Repair |
| Aftermarket Maneuvering Thrusters | Maneuverability | Space Transports Repair |
| Hyperdrive Tuning Kit | Hyperdrive | Space Transports Repair |

### Wildspace Ship Mods

Three additional mod types unlock the Wildspace resource operations (`mine`,
`salvage`, `refine`). All are crafted by **Venn Kator** (Space Transports
Repair):

| Mod | Effect | Craft Diff | Resources | Rep Gate |
|-----|--------|-----------|-----------|----------|
| **Mining Laser Mk1** | +2D mining; −25% mine cooldown | 16 | 12 metal + 4 energy | None |
| **Mining Laser Mk2** | +3D mining; −40% cooldown; deep mining on critical | 20 | 24 metal + 8 energy + 2 rare | Hutt Cartel 25+ |
| **Reinforced Salvage Arm Mk1** | +2D salvage; +1 component per run | 16 | 8 metal + 4 composite | None |
| **Reinforced Salvage Arm Mk2** | +3D salvage; +2 components; intact extraction | 20 | 16 metal + 8 composite + 2 rare | Republic 25+ |
| **Onboard Refinery** | Enables in-flight `refine` (raw → refined) | 18 | 10 metal + 6 energy + 4 composite | None |

Mining Laser Mk2 unlocks **deep mining** — a critical on the `mine` roll yields a
bonus rare-resource draw Mk1 can't reach. Salvage Arm Mk2 adds **intact
extraction** — a chance to recover a complete undamaged component from a
derelict. Mk2 mods replace their Mk1 (one mod slot per type — uninstall the Mk1
first); the Onboard Refinery uses its own slot.

---

## 12. Ship's Log and Titles

The ship's log tracks milestones across categories — zones visited, ships
scanned, anomalies resolved, planets landed, pirate kills, smuggling runs, trade
runs. Crossing a threshold awards a CP milestone bonus (these bypass the weekly
tick cap), and the top threshold in a category earns a **title**:

| Title | Requirement | CP |
|-------|------------|----|
| Explorer | Visit 16 distinct zones | 50 |
| Spotter | Scan 19 distinct ship types | 30 |
| Archaeologist | Resolve all 7 anomaly types | 30 |
| Galactic Traveler | Land on 4 planets | 20 |
| Pirate Hunter | 100 pirate kills | 50 |
| Ace Smuggler | 50 smuggling runs | 50 |
| Merchant Prince | 50 profitable trade runs | 30 |

There are lower milestone ticks along the way too (5/10 zones, 5/10 ships, 10/50
pirates, 5/20 smuggling runs, 10 trade runs) that pay smaller CP without a title.
Titles display on your character sheet and in the `+who` list.

---

## 13. NPC Space Traffic

NPC ships work the spacelanes — freighters hauling cargo, Republic clone patrols
checking transponders, Hutt-flagged smugglers, pirate raiders, and bounty
hunters stalking both. You'll meet them as you navigate. Pirates tail and attack
in lawless deep space; Republic patrols hail and inspect in contested zones; the
Hutts tax rather than fight, if you've got standing with the Cartel. Restricted
worlds (Kamino) and active fronts (Geonosis) run scripted spawns rather than
random traffic.

---

## 14. Web Client Space HUD

The web client provides a rich space interface:
- **Zone Map SVG** — Visual map with your location highlighted
- **Tactical Radar SVG** — Real-time display of ships in your zone
- **Ship Status Schematic** — SVG showing system states
- **Power Allocation Bar** — Visual distribution of reactor power
- **Captain's Order Badge** — Active tactical order display
- **Station-Aware Quick Buttons** — Context buttons that change with your station

---

## 15. Space Commands Quick Reference

| Category | Commands |
|----------|----------|
| **Ship Management** | `+ship`, `+ship/list`, `+ship/info`, `+ship/mine`, `+ship/rename`, `+ship/mods`, `+ship/install`, `+ship/uninstall`, `+ship/repair`, `board`, `disembark`, `pay` |
| **Crew Stations** | `pilot`, `copilot`, `gunner`, `engineer`, `navigator`, `commander`, `sensors`, `vacate` |
| **Navigation** | `course`, `hyperspace`, `land`, `launch` |
| **Combat** | `fire`, `lockon`, `close`, `flee`, `tail`, `outmaneuver`, `evade`, `jink`, `barrelroll`, `loop`, `slip` |
| **Ship Operations** | `scan`, `deepscan`, `shields`, `damcon`, `power`, `coordinate`, `assist`, `order` |
| **Economy / Wildspace** | `market`, `buy`, `sell`, `mine`, `salvage`, `refine`, `hail`, `transponder` |
| **Admin** | `@spawn` (staff) |
