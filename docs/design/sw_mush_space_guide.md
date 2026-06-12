# SW_MUSH — The Spacer's Handbook
## A New Player's Guide to Space, Ships, and the Stars Beyond

*Welcome aboard, spacer. Whether you're a smuggler running glitterstim through the Kessel Approach, a hotshot pilot chasing TIE Interceptors through asteroid fields, or an engineer keeping a battered freighter flying with spit and wiring, this guide covers everything you need to know about taking to the stars in SW_MUSH.*

*This game uses the West End Games Star Wars D6 Revised & Expanded ruleset. If you've rolled a Wild Die before, you're already halfway there.*

---

## Part One — Your Ship

### What's Out There

The galaxy has 19 ship templates spread across five categories. Every ship has a **scale** — either starfighter or capital — that fundamentally changes how it fights and takes damage.

**Light Freighters** — the workhorses of the Outer Rim. Room for cargo, room for passengers, room for trouble.

| Ship | Hull | Shields | Speed | Maneuver | Hyperdrive | Cargo | Mod Slots | Price |
|------|------|---------|-------|----------|------------|-------|-----------|-------|
| YT-1300 Transport | 4D | 1D | 4 | 1D | x2 | 100t | 5 | 100,000cr |
| Ghtroc 720 Freighter | 4D | 1D | 3 | 1D | x2 | 135t | 4 | 98,500cr |
| YT-2400 Transport | 4D+2 | 2D | 5 | 1D+2 | x2 | 150t | 5 | 130,000cr |

The YT-1300 is the classic — affordable, customizable, and tough enough to take a beating. The Ghtroc 720 carries more cargo at the cost of speed. The YT-2400 is the premium option with better shields, dual turrets, and extra hull.

**Rebel Starfighters** — fast, shielded, and deadly in a dogfight.

| Ship | Hull | Shields | Speed | Maneuver | Weapons | Price |
|------|------|---------|-------|----------|---------|-------|
| X-Wing | 4D | 1D+2 | 8 | 3D | 4 fire-linked lasers (6D), proton torps (9D) | 150,000cr |
| Y-Wing | 4D | 1D+2 | 7 | 2D | 2 fire-linked lasers (5D), proton torps (9D), ion turret (4D) | 135,000cr |
| A-Wing | 2D+2 | 1D | 12 | 4D | 2 lasers (5D), concussion missiles (7D) | 175,000cr |
| B-Wing | 3D | 2D | 6 | 1D+1 | Laser (7D), proton torps (9D), 3 ion cannons (4D), 2 auto blasters (3D) | 220,000cr |

The A-Wing is the fastest thing in the sky but fragile as glass. The B-Wing is a flying arsenal — ion cannons to disable, torpedoes to destroy. The X-Wing is the all-rounder. The Y-Wing is the dependable workhorse with that invaluable ion cannon turret.

**Imperial Starfighters** — fast, unshielded, and expendable. The Empire doesn't believe in ejection seats.

| Ship | Hull | Shields | Speed | Maneuver | Weapons |
|------|------|---------|-------|----------|---------|
| TIE/ln Fighter | 2D | None | 9 | 2D | 2 fire-linked lasers (5D) |
| TIE Interceptor | 3D | None | 11 | 3D+2 | 4 fire-linked lasers (6D) |
| TIE Bomber | 4D | None | 6 | 1D+2 | 2 lasers (3D), proton torps (9D), concussion missiles (7D) |

TIEs have no shields and no hyperdrive — they're tethered to a carrier or base. The Interceptor is terrifyingly fast and maneuverable, but one solid hit and it's scrap. Flying one is a statement about your confidence (or your recklessness).

**Independent & Patrol Ships** — for bounty hunters, mercenaries, and those who fly alone.

| Ship | Hull | Shields | Speed | Maneuver | Notable |
|------|------|---------|-------|----------|---------|
| Z-95 Headhunter | 3D | 1D | 7 | 1D | Cheap at 40,000cr, no hyperdrive |
| Firespray Patrol Craft | 5D | 2D | 7 | 1D | Tractor beam, tough hull, 3 mod slots |

The Firespray is a bounty hunter's dream — tractor beam to snag runners, heavy hull to survive the fight, and enough mod slots to make it your own. The Z-95 is what you fly when you can't afford anything better.

**Shuttles** — military transports built to deliver troops under fire.

| Ship | Hull | Shields | Speed | Crew | Passengers |
|------|------|---------|-------|------|------------|
| Lambda Shuttle | 5D | 2D+2 | 5 | 4 | 20 |
| Sentinel Landing Craft | 5D | 2D | 6 | 5 | 54 |

**Capital Ships** — these are a different class entirely. Capital-scale weapons, capital-scale problems.

| Ship | Hull | Shields | Speed | Crew | Weapons | Mod Slots |
|------|------|---------|-------|------|---------|-----------|
| CR90 Corvette | 4D | 2D | 6 | 30 | 6 turbolaser batteries | 6 |
| Nebulon-B Frigate | 5D+1 | 2D | 4 | 920 | 12 turbolasers, 12 lasers, 2 tractors | 8 |
| Imperial Star Destroyer | 7D | 3D | 6 | 36,810 | 60 turbolasers, 60 heavy turbolasers, 10 tractors, 20 ion cannons | 10 |

Capital ships operate on a completely different scale. A 6D difference separates starfighter-scale and capital-scale — meaning a starfighter's 6D laser does effectively nothing against a Star Destroyer's hull, while a turbolaser vaporizes a snubfighter. More on scale in the combat section.

### Understanding Ship Stats

Every stat on your ship matters. Here's what they mean in practice:

**Hull** is your ship's structural integrity, measured as a dice pool. When you take damage, the attacker's damage roll is compared against your hull roll. If damage exceeds hull, bad things happen — from light damage all the way to destruction.

**Shields** add dice to your hull roll when absorbing hits. They're your first line of defense. On capital ships, shield dice can be redistributed between arcs (front, rear, left, right) using the `shields` command.

**Speed** determines how fast you move in sublight. Higher speed means you can close distance or flee more effectively. Speed also factors into chase mechanics.

**Maneuverability** is your dodge dice in space. When someone shoots at you and your pilot evades, maneuverability is the base pool. A 4D A-Wing is dramatically harder to hit than a 1D freighter.

**Hyperdrive Multiplier** determines hyperspace travel time. Lower is faster — a x1 drive is twice as fast as a x2. The legendary Millennium Falcon runs a x0.5. Ships with a multiplier of 0 (like TIE fighters) have no hyperdrive at all.

**Fire Control** is a bonus added to your gunnery roll when shooting. Higher fire control means more accurate weapons. This is separate from your character's Starship Gunnery skill — the two add together.

**Fire Arc** determines which direction a weapon can shoot: front, rear, left, right, or turret. Turret weapons can fire in any direction. A front-only weapon can't shoot at someone behind you.

**Mod Slots** determine how many custom components can be installed on your ship. Freighters have 4-5 slots for tinkering; military fighters have 1-2 (they're already optimized).

---

## Part Two — Getting Into Space

### Boarding and Launching

Before you can fly, you need to get aboard. Head to a docking bay and find your ship.

```
board                      -- board a ship in the current room
```

Once aboard, you're standing in the ship's bridge. From here, you can take a crew station and prepare for launch.

```
launch                     -- take off from the docking bay
```

Launching puts your ship into the local dock zone (e.g., `tatooine_dock`). From there, you navigate outward through the zone graph.

**Important:** If you have an active smuggling job, launching triggers a patrol encounter check. Imperial patrols may scan your cargo. Keep your wits about you.

### Landing

When you're ready to come back down, you need to be in an orbit or dock zone above a planet.

```
land                       -- land at the planet below you
```

This returns you to the planet's docking bay. You can then `disembark` to leave the ship.

---

## Part Three — Crew Stations

A ship is only as good as its crew. SW_MUSH has seven crew stations, and each one has a distinct role. On a solo freighter, you might be doing everything yourself. On a capital ship, every station should be manned.

### Taking a Station

```
pilot                      -- take the pilot station
gunner                     -- take a gunner station (gunner 2 for weapon #2)
copilot                    -- take the copilot station
engineer                   -- take the engineer station
navigator                  -- take the navigator station
commander                  -- take the commander station
sensors                    -- take the sensors station
vacate                     -- leave your current station
```

### The Seven Stations

**Pilot** — the most important station on the ship. The pilot controls movement, evasion, and navigation. Without a pilot, the ship doesn't move.

Key commands: `course`, `evade`, `close`, `fleeship`, `jink`, `barrelroll`, `loop`, `slip`, `hyperspace`, `launch`, `land`

Key skills: Starfighter Piloting (or Capital Ship Piloting for big ships), Space Transports

**Gunner** — you shoot things. On capital ships, each weapon group has its own gunner station. You can only fire the weapon you're stationed at.

Key commands: `fire`, `lockon`

Key skills: Starship Gunnery (or Capital Ship Gunnery)

**Copilot** — the backup pilot. You can assist the pilot and help with scanning and navigation. The copilot uses the `assist` command to give the pilot bonus dice.

Key commands: `assist`, `scan`, `course`

Key skills: Space Transports, Sensors

**Engineer** — keeps the ship running. Damage control is your bread and butter. When systems fail, you're the one crawling through conduits with a hydrospanner.

Key commands: `damcon`, `+ship/repair`

Key skills: Space Transports Repair (or Capital Ship Repair), Starship Weapon Repair

**Navigator** — plots hyperspace courses. A good navigator gets you there faster and safer. A bad one gets you lost in an asteroid field. The navigator at the sensors station grants +1D to astrogation rolls.

Key commands: `hyperspace`, `scan`

Key skills: Astrogation, Sensors

**Commander** — directs the crew. The `coordinate` command gives a bonus to another crew member's next roll. On well-crewed ships, the Commander is the difference between a coordinated crew and a panicking mob.

Key commands: `coordinate`, `scan`

Key skills: Command, Tactics

**Sensors** — the ship's eyes and ears. The sensors operator scans for contacts, identifies ships, and detects hidden anomalies. Taking the sensors station grants a +2D bonus to scan rolls.

Key commands: `scan`, `deepscan`

Key skills: Sensors

---

## Part Four — Navigation

### The Zone Map

Space in SW_MUSH is organized into **zones** — named areas connected in a graph. There are no room objects or compass directions in space. Instead, you navigate between zones using the `course` command.

The galaxy currently spans four planets connected by three hyperspace lanes:

```
corellian_trade_spine ──── corellia_deep_space ── corellia_orbit ── corellia_dock
        │
outer_rim_lane_1 ──────── tatooine_deep_space ── tatooine_orbit ── tatooine_dock
        │
outer_rim_lane_2 ──────── nar_shaddaa_deep_space ── nar_shaddaa_orbit ── nar_shaddaa_dock
        │
outer_rim_lane_3 ──────── kessel_approach [HEAVY HAZARD] ── kessel_orbit ── kessel_dock
```

Each planet has four zones arranged in a chain: dock → orbit → deep space → hyperspace lane. The hyperspace lanes connect the planetary systems together.

**Zone types:**

- **Dock** — where you land and launch. Close to the planet's surface. Safe harbor.
- **Orbit** — low planetary orbit. The transition point between ground and space.
- **Deep Space** — open void between a planet and the hyperspace lanes. NPC traffic spawns here. Anomalies can appear.
- **Hyperspace Lane** — the great spacelanes connecting star systems. The Corellian Trade Spine is one of the galaxy's busiest routes.

### Sublight Navigation

To move between adjacent zones, use the `course` command. Only the pilot can set course.

```
course                     -- show your current zone and adjacent zones
course <zone name>         -- set course for an adjacent zone
course cancel              -- cancel current transit
```

Transit takes real time depending on the distance:

- Dock ↔ Orbit: 15 seconds
- Orbit ↔ Deep Space: 20 seconds
- Deep Space ↔ Hyperspace Lane: 25 seconds

During transit, your ship is removed from the combat grid — you can't fire or be fired upon. On arrival, a piloting skill check determines how cleanly you enter the zone. A critical success grants a brief sensors bonus.

### Hyperspace Travel

To jump between star systems, you need a hyperdrive and a successful astrogation check.

```
hyperspace                 -- list available destinations
hyperspace <destination>   -- jump to a destination
```

**How it works:**

1. Your navigator (or pilot, if no navigator) makes an Astrogation skill check. The base difficulty is Moderate (11-15).
2. If the check succeeds, the ship enters hyperspace transit. All space commands are blocked except `+shipstatus` — you're hurtling through an alternate dimension at superluminal speeds.
3. Travel time depends on the route distance and your hyperdrive multiplier. A x1 drive takes the base time; a x2 drive takes double.
4. On arrival, you drop out of hyperspace in the destination planet's orbit zone.

**Base travel times (x1 hyperdrive):**

| Route | Time |
|-------|------|
| Tatooine ↔ Nar Shaddaa | 60 seconds |
| Nar Shaddaa ↔ Kessel | 45 seconds |
| Tatooine ↔ Kessel | 90 seconds |
| Tatooine ↔ Corellia | 120 seconds |
| Nar Shaddaa ↔ Corellia | 90 seconds |
| Kessel ↔ Corellia | 120 seconds |

Multiply these by your hyperdrive class. A x2 freighter takes twice as long. That's the price of flying civilian hardware.

**What can go wrong:**

- **Fumble** — misjump! You drop out of hyperspace in a random zone, roll on the hazard table, and burn full fuel. This is the nightmare scenario.
- **Failure** — the jump aborts safely. No fuel consumed, no movement.
- **Success** — normal jump, normal travel time.
- **Critical success** — fuel cost is halved. Your navigator found an efficient route.

Some zones have a **nav modifier** that increases astrogation difficulty. The Kessel Approach, for instance, is notoriously dangerous to jump from — the gravity wells of The Maw make plotting a course a white-knuckle affair.

**No nav computer?** Add +30 to the difficulty. Don't try this unless you're exceptionally skilled or exceptionally desperate. Astromech droids can substitute for a nav computer.

---

## Part Five — Space Combat

### The Flow of Battle

Space combat follows the WEG D6 sequence:

1. **Declare actions** — everyone states what they're doing this round, in order of lowest Dexterity to highest.
2. **Declare reactions** — evasions, shield adjustments, and other defensive moves.
3. **Resolve actions** — rolls happen in order of haste (highest to lowest).
4. **Calculate damage** — for every hit, compare damage dice vs. hull/shield dice.

In practice, the MUSH handles the mechanical sequencing. You type commands and the system resolves them.

### Attacking

```
fire <target>              -- fire your weapon at a target
fire <target> with <weapon> -- fire a specific weapon (capital ships)
fire <target> 2            -- fire weapon #2 at a target
```

Your attack roll is: **Starship Gunnery skill + Fire Control dice**

This is compared against the target's difficulty — either a flat difficulty based on range, or the target's evasion roll if they dodged. Range matters:

- Point Blank: Very Easy (3-5)
- Short Range: Easy (6-10)
- Medium Range: Moderate (11-15)
- Long Range: Difficult (16-20)

### Lock-On Targeting

```
lockon <target>            -- begin locking on to a target
```

Lock-on gives you a cumulative +1D bonus to fire control per round you maintain the lock, up to +3D maximum. This represents your targeting computer tracking the target's movement pattern. It's devastating if you can maintain it — but if your target breaks line of sight or you switch targets, the lock resets.

### Evasive Maneuvers

The pilot is your best defense. When someone shoots at your ship, the pilot can evade.

```
evade                      -- perform a general evasive maneuver
```

Your evasion roll uses **Starfighter Piloting + Maneuverability dice**. This becomes the new difficulty number for anyone shooting at you that round — even if it's worse than the base range difficulty. Sometimes a poor evade makes you easier to hit. Choose wisely.

**Advanced evasive maneuvers** are specialized moves with specific effects:

```
jink                       -- quick lateral dodge
barrelroll                 -- roll to throw off a pursuer's aim
loop                       -- loop over an attacker (Immelmann turn)
slip                       -- sideslip to change facing
```

Each of these has a different difficulty and effect. A jink is the simplest — a quick lateral juke. A loop is a dramatic Immelmann turn that can flip your position relative to an attacker. Failed maneuvers can trigger the **hazard table**.

### The Hazard Table

When an evasive maneuver goes badly wrong, the game rolls 2d6 on the hazard table. There are 11 possible outcomes, ranging from minor inconveniences to catastrophic damage:

- **2-3:** Hyperdrive cutout — damage sustained
- **4:** Radiation fluctuations
- **5-6:** Hyperdrive cutout, no damage
- **7:** Off-course
- **8:** Mynocks (parasitic pests clinging to the hull)
- **9-10:** Close call (near miss with debris)
- **11:** Collision — heavy damage sustained
- **12:** Other mishap (GM discretion)

The hazard table keeps space dangerous. Even a routine evasion can have consequences if you roll poorly.

### Closing and Fleeing

Space combat has a spatial element. Ships are at different ranges from each other, and the pilot can change that.

```
close <target>             -- close the range with a target
fleeship                   -- attempt to break away from combat
```

Closing range is an opposed piloting check. If you succeed, you move one range band closer (long → medium → short → point blank). Fleeing is the reverse — success puts you one band further away, and if you're already at long range, you escape.

### Tailing and Outmaneuvering

Tailing is a persistent tactical advantage. When you're behind an enemy, they can't use rear-arc weapons against you, and you get bonuses.

```
tail <target>              -- attempt to get behind a target
outmaneuver                -- try to shake a tail
```

Tailing is an opposed piloting check. Once you're tailing someone, you maintain that advantage until they outmaneuver you or you break off. A persistent tail is one of the most powerful positions in space combat — it's the Star Wars equivalent of getting on someone's six.

### Damage

When a weapon hits, the attacker rolls damage dice and the defender rolls hull dice (plus any remaining shield dice). The comparison:

| Damage vs. Hull | Normal Weapons | Ion Cannons |
|----------------|----------------|-------------|
| 2× DR < SR | No effect | No effect |
| DR < SR | Lightly damaged | Lose shield generator or ionized -1D |
| DR ≥ SR | Heavily damaged | -2D ionization |
| DR ≥ 2× SR | Severely damaged | Dead controls; -3D ionization next round |
| DR ≥ 3× SR | Destroyed | Destroyed |

When a ship is severely damaged, roll on the **System Damage table** to determine what breaks:

1. **Ion drives** — no speed, no maneuver rolls
2. **Nav computer** — astrogation is Very Difficult until repaired
3. **Hyperdrives** — can't enter hyperspace
4. **Weapon system** — one weapon offline
5. **Shields** — no shield rolls
6. **Lateral thrusters** — maneuverability drops to 0

### Ion Cannons

Ion weapons don't destroy ships — they disable them. Ion damage causes **ionization penalties** that subtract dice from all the ship's actions. A fully ionized ship is a sitting duck with dead controls. This makes ion cannons essential for anyone who wants to capture rather than kill — bounty hunters, pirates, and Imperial patrols all love them.

Ion penalties decay over time (tick-based), so ionization is temporary. But while it lasts, your ship is in serious trouble.

### Tractor Beams

Tractor beams capture ships and reel them in. It's a contested roll — the tractor beam operator rolls their skill against the target pilot's piloting roll.

If captured, the target ship is held. Every 10 seconds, the tractor auto-reels the captured ship one range band closer. At close range, the capturing ship can board.

The `resist` command lets a held ship try to break free with a piloting check each round.

### Shields Management

On capital ships, shield dice can be redistributed between arcs:

```
shields                    -- show current shield distribution
shields front 3 rear 1    -- redistribute shields between arcs
```

This lets the engineer or pilot strengthen shields on the side taking fire. A Star Destroyer being flanked might pull all shields to one side. A corvette running from fighters might stack everything to the rear. Shield management is a constant tactical decision.

### Scale — Starfighters vs. Capital Ships

This is one of the most important concepts in space combat. There is a **6D modifier** between adjacent scales:

- A starfighter shooting at a capital ship: **+6D to hit**, but **-6D to damage**. You can land the hit, but your little lasers barely scratch the armor.
- A capital ship shooting at a starfighter: **-6D to hit**, but **+6D to damage**. If a turbolaser hits an X-Wing, the X-Wing is vapor. But good luck actually hitting something that nimble.

This is why the Rebels use snubfighters — they're nearly impossible for capital weapons to track. And it's why capital ships carry TIE squadrons — you need starfighters to fight starfighters.

**Capital ship gunnery** uses different skills: Capital Ship Gunnery instead of Starship Gunnery, Capital Ship Piloting instead of Starfighter Piloting, Capital Ship Shields instead of Starship Shields.

### Damage Control

When your ship takes damage, the engineer gets to work.

```
damcon                     -- attempt damage control repairs
+ship/repair               -- perform structural repairs (out of combat)
```

Damage control uses the `resolve_repair_check()` system. Results scale with your margin of success:

- **Critical success** — 2 hull points repaired
- **Normal success** — 1 hull point repaired
- **Near miss (margin ≥ -4)** — ship stabilized, no repair
- **Fumble** — catastrophic failure, things get worse

The repair skill used depends on ship scale: Space Transports Repair for starfighter-scale ships, Capital Ship Repair for capital ships.

---

## Part Six — Scanning and Sensors

### Basic Scanning

The `scan` command is your window to the space around you. Anyone aboard can scan, but the sensors operator gets a +2D bonus.

```
scan                       -- perform a sensor sweep of the zone
```

Scan results depend on your skill roll:

- **Fumble** — sensors go offline momentarily. You see nothing.
- **Failure** — you see ship names and range only. Minimal information.
- **Success** — you see the standard loadout: ship type, weapons, shields, speed.
- **Critical success** — deep scan. Full stats plus cargo manifest flags.

Zones with a `sensor_penalty` (like dense asteroid fields) subtract dice from your scan roll, making it harder to get good readings.

### Deep Scanning for Anomalies

This is where the sensors station really shines. Anomalies are hidden points of interest scattered through space — derelict ships, distress signals, pirate nests, mineral veins, and more. Finding them requires iterative scanning.

```
deepscan                   -- scan for anomalies in your current zone
deepscan <id>              -- focus on a specific detected anomaly
```

The process works like detective work:

1. **First scan** — you detect that something is out there. Signal type: Unknown. Resolution: 33%.
2. **Second scan** — the signal resolves further. You learn the general type (metallic debris, energy signature, etc.). Resolution: 66%.
3. **Third scan** — fully resolved. You know exactly what it is and can navigate to it.

A critical success on any scan skips one step — an expert sensors operator can fully resolve an anomaly in two scans instead of three.

**Seven anomaly types exist:**

| Type | Chance | Scans Needed | What You Find |
|------|--------|-------------|---------------|
| Derelict Ship | 30% | 3 | Salvageable components, crafting resources, credits |
| Distress Signal | 20% | 2 | Rescue opportunity — or pirate ambush |
| Hidden Cache | 15% | 3 | Credits, rare resources, possible schematics |
| Pirate Nest | 15% | 2 | 2-3 hostile pirates, good salvage on victory |
| Asteroid Mineral Vein | 10% | 2 | High-quality metal and rare resources |
| Imperial Dead Drop | 5% | 4 | Encrypted data, big credits, but Imperial patrol risk |
| Mynock Colony | 5% | 1 | Hull parasites. Annoying, not deadly |

Anomalies spawn every 5 minutes in zones where player ships are present. Deep space zones have the highest spawn rate (15%), while hyperspace lanes are lowest (5%) — things move too fast there. Dock zones never spawn anomalies.

### Salvage

After finding a derelict or destroying an NPC ship, you can salvage the wreckage.

```
salvage                    -- salvage components from nearby wreckage
```

Salvage uses a Technical attribute check. The materials you recover — metal scrap, energy cells, composite plating, rare components — feed directly into the crafting system. A salvage-focused crew can supply a crafter with steady resources by hunting pirates and exploring derelicts.

Destroyed NPC ships leave wrecks for 2 minutes before the debris disperses. Derelict anomalies persist for 30 minutes.

---

## Part Seven — Environmental Hazards

### Asteroid Fields

Certain zones are marked as hazardous. The Kessel Approach is the prime example — tagged as HEAVY HAZARD with dense asteroid fields.

When you enter a hazardous zone, you get a warning. If you remain in a heavy asteroid zone, every 30 seconds your pilot must make an Easy piloting check. Failure means a hull scrape (1 point of hull damage). This discourages loitering — transit through dangerous zones quickly.

Hazardous zones also impose sensor penalties (fewer dice on scan rolls) and navigation modifiers (higher astrogation difficulty when jumping from that zone).

### NPC Traffic

Space isn't empty. The NPC space traffic system spawns five archetypes of ships that transit between zones autonomously:

- **Traders** — civilian freighters minding their business
- **Patrols** — Imperial customs ships scanning for contraband
- **Pirates** — hostile ships looking for prey
- **Bounty Hunters** — tracking targets with active bounties
- **Military** — Imperial Navy ships on patrol

During world events like an Imperial Crackdown, patrol spawn rates double. The Director AI system influences traffic patterns based on the evolving state of the galaxy.

---

## Part Eight — Communications

### Ship-to-Ship Comms

```
hail <target>              -- hail another ship
comms <message>            -- broadcast on an open frequency
```

Hailing opens a communication channel with another ship. Comms broadcasts to all ships in your zone. These are essential for roleplay in space — negotiate with pirates, coordinate with allies, or bluff your way past an Imperial patrol.

---

## Part Nine — The Economy of Space

### Buying Ships

```
buy <ship template>        -- purchase a ship at a docking bay
+credits                   -- check your credit balance
```

Ship purchases use the Bargain skill. The `buy` command runs an opposed Bargain check against the NPC vendor — a good haggler can negotiate better prices. The system auto-detects the NPC's Bargain skill from the vendor in the room.

### Smuggling

Smuggling is one of the primary credit-earning activities in space. The smuggling job board offers jobs across four tiers of risk and reward. With the interplanetary route system, smuggling runs now cross planetary boundaries — pick up glitterstim on Kessel and deliver it to Nar Shaddaa.

When carrying contraband, launch triggers a patrol check. Arriving at your destination planet triggers another. Get caught and you face fines, cargo seizure, or worse. The `smugdeliver` command only succeeds if you're docked at the right planet.

### Missions in Space

The mission board offers space-specific mission types:

- **Patrol** — fly through specified zones and scan for hostiles
- **Escort** — protect an NPC convoy through dangerous space
- **Intercept** — hunt down a specific NPC target
- **Survey Zone** — scan and report on a remote zone's contents

These missions use the same mission board system as ground missions, completed with skill checks and paying out credits and CP ticks.

---

## Part Ten — Ship Customization

### Modification Slots

Every ship has a limited number of mod slots. Freighters have the most room to tinker (4-5 slots); military ships are already optimized (1-2 slots). Installing components costs mod slots AND cargo capacity — those engine boosters take up space.

### Component Types

Seven types of craftable ship components exist, each modifying a different stat:

| Component | Stat Modified | Max Boost |
|-----------|---------------|-----------|
| Engine Booster | Speed (+1 per mod) | +2 speed |
| Shield Generator | Shields (+1 pip per mod) | +1D+2 |
| Weapon Upgrade | Fire Control on one weapon (+1 pip) | +1D+2 |
| Armor Plating | Hull (+1 pip per mod) | +1D+2 |
| Sensor Suite | Sensors skill bonus (+1 pip) | +1D |
| Hyperdrive Tuning | Hyperdrive multiplier (-0.5 per mod) | -1.0 |
| Maneuvering Thrusters | Maneuverability (+1 pip per mod) | +1D+2 |

Components are crafted using the existing crafting pipeline — survey for resources, gather materials, assemble the component with a skill check. Quality matters: a well-crafted component gives better stat boosts.

The salvage-to-mod pipeline connects exploration to ship improvement: hunt anomalies → salvage wrecks → craft components → install on your ship.

---

## Part Eleven — Advanced Systems

### Power Allocation (Engineer)

The engineer controls power distribution across four ship systems: engines, shields, weapons, and sensors. Each ship has a reactor budget, and the engineer allocates points between systems using the `power` command.

```
power                      -- show current power allocation
power engines +1           -- shift power to engines
power silent               -- enter silent running mode
```

Overcharging a system (giving it extra power) grants bonuses: +1 speed per extra engine point, +1 pip shields, +1 pip fire control, +1D sensors. But power is zero-sum — boosting one system means starving another.

**Silent Running** is a special preset: engines at minimum, shields off, weapons off, sensors off. The ship becomes very difficult to detect (+3D to sensor difficulty against you). Essential for smugglers, spies, and anyone who doesn't want to be found.

Without an engineer aboard, the ship runs on default power allocation and cannot be adjusted. This makes the engineer essential for every serious flight.

### Captain's Orders (Commander)

The Commander station gains tactical orders that apply ship-wide bonuses and tradeoffs:

```
order                      -- show current tactical order
order <name>               -- issue a tactical order
order cancel               -- cancel the current order
```

| Order | Bonus | Tradeoff |
|-------|-------|----------|
| Battle Stations | +1D fire control to all gunners | -1D maneuverability |
| Evasive Pattern | +2D maneuverability for pilot | -1D fire control to all gunners |
| All Power Forward | +2 speed | -1D shields, no rear weapons |
| Hold the Line | +2D shields | -2 speed, cannot flee |
| Silent Running | +3D sensor stealth | No weapons, shields off |
| Boarding Action | +1D melee/brawl for boarding crew | -1D piloting |
| Concentrate Fire | +2D damage for one weapon | Other weapons can't fire |
| Coordinate | +1D to all crew checks | No tradeoff |

Orders take effect immediately and persist until changed, cancelled, or the Commander vacates. Issuing an order requires a Command skill check (Easy, difficulty 8). On a fumble, a random order takes effect for 30 seconds — chaos on the bridge.

### Transponder Codes

Every ship broadcasts a transponder code identifying its name and type. But not every code tells the truth.

```
transponder                -- show current transponder status
transponder false <name>   -- set a false transponder (Con check)
transponder reset          -- restore real transponder
```

Running a false transponder is a Class Two Imperial customs infraction. If a scanning ship's sensors beat your Con roll, the forgery is detected. On a critical scan success, your real identity is revealed.

Imperial Customs enforces five infraction classes, from safety violations (Class 5, small fine) to espionage (Class 1, execution). False transponders sit at Class 2 — up to 10,000 credits fine and possible ship seizure. But a well-timed Bargain check can reduce fines through "personal benefit fees" — this is the Star Wars galaxy, after all.

---

## Part Twelve — Practical Advice for New Spacers

### Your First Flight

1. Start in Mos Eisley. Find the Docking Bay.
2. If you own a ship, `board` it. If not, `buy yt_1300` to purchase a YT-1300 (100,000 credits — check `+credits` first).
3. `pilot` to take the pilot station.
4. `launch` to lift off. You're now in `tatooine_dock`.
5. `course tatooine orbit` to navigate to orbit.
6. `scan` to see what's around you.
7. `course tatooine deep space` to head into open space.
8. When ready to return: `course tatooine orbit`, then `course tatooine dock`, then `land`.

### Your First Hyperspace Jump

1. From orbit or deep space, type `hyperspace` to see available destinations.
2. `hyperspace corellia` to jump to Corellia.
3. Wait through the transit time (your hyperdrive class × base travel time).
4. You'll arrive in Corellia orbit. `land` to dock.

### Your First Fight

1. `scan` to identify targets. Look for NPC pirates.
2. `close <target>` to close the range.
3. `fire <target>` to open fire.
4. If they shoot back, `evade` to dodge.
5. Keep firing until the target is destroyed.
6. `salvage` the wreck for resources.

### Tips for Survival

- **Always scan before jumping.** Know what's in the zone before you commit.
- **Keep your engineer aboard.** Damage control saves lives.
- **Don't loiter in hazardous zones.** Asteroid fields deal damage over time.
- **Lock-on is powerful.** Three rounds of lock-on gives +3D to your next shot. That's enormous.
- **Know when to flee.** `fleeship` is not cowardice — it's survival. You can't salvage anything if you're dead.
- **Crew matters.** A full crew on a freighter (pilot, gunner, engineer) is dramatically more effective than a solo operator doing everything with multi-action penalties.
- **Watch your scale.** Don't pick fights across scale boundaries unless you know what you're doing. A starfighter vs. a Star Destroyer is a very bad idea without a squadron backing you up.

### Key Skills for Spacers

| Skill | Attribute | Used For |
|-------|-----------|----------|
| Starfighter Piloting | Mechanical | Piloting fighters and small ships |
| Space Transports | Mechanical | Piloting freighters and transports |
| Capital Ship Piloting | Mechanical | Piloting capital-scale vessels |
| Starship Gunnery | Mechanical | Firing starfighter-scale weapons |
| Capital Ship Gunnery | Mechanical | Firing capital-scale weapons |
| Astrogation | Mechanical | Plotting hyperspace jumps |
| Sensors | Mechanical | Operating sensors, scanning, deep scanning |
| Starship Shields | Mechanical | Managing shield distribution |
| Space Transports Repair | Technical | Repairing freighter-scale ships |
| Starship Weapon Repair | Technical | Repairing weapons systems |
| Capital Ship Repair | Technical | Repairing capital-scale ships |
| Bargain | Perception | Buying ships, negotiating with vendors |
| Con | Perception | Running false transponder codes |
| Command | Perception | Issuing captain's orders |

### Quick Command Reference

**Getting Around:**
`board`, `disembark`, `launch`, `land`, `course`, `hyperspace`

**Crew Stations:**
`pilot`, `gunner`, `copilot`, `engineer`, `navigator`, `commander`, `sensors`, `vacate`

**Combat:**
`fire`, `lockon`, `evade`, `jink`, `barrelroll`, `loop`, `slip`, `close`, `fleeship`, `tail`, `outmaneuver`, `shields`, `damcon`

**Information:**
`scan`, `deepscan`, `+shipstatus` (alias: `ss`), `+shipinfo`, `+ships`, `+myships`, `+credits`

**Economy:**
`buy`, `salvage`, `hail`, `comms`, `pay`

**Admin/Misc:**
`@spawn`, `@setbounty`, `resist`, `coordinate`, `assist`

---

*"She may not look like much, but she's got it where it counts, kid."*

*Good luck out there, spacer. The stars are waiting.*
