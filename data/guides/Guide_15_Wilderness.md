---
category: galaxy
order: 5
summary: "The open desert, canyons, and undercity sprawl outside the built rooms. Regions, landmarks, movement, harvesting, and how the wild fits together with hazards, anomalies, and territory."
tags: ["wilderness", "exploration", "landmarks", "regions", "harvest", "dune sea", "jundland", "coruscant underworld", "geonosis"]
---

# Wilderness

**Parsec — WEG D6 Revised & Expanded**
**BTGlass80 — July 2026**
**Guide Version 1.0**

---

## How to Read This Guide

Most of the game happens in hand-built rooms — cantinas, hangar bays, Senate corridors, each one authored down to the doorframe. The **wilderness** is the other half of the galaxy: the open Dune Sea, the canyon badlands of the Jundland Wastes, the lightless sprawl below Coruscant's undercity, the red dune country of Geonosis's E'Y-Akh. These are **coordinate-grid regions** — you don't walk from named room to named room, you walk a compass across a real map, tile by tile, and the desert (or the dark) reads back at you as you go.

This guide covers the wilderness as a whole: what it is and how it differs from the city map, how you get into a region and move around inside one, the four regions that exist today, the roster of named **landmarks** scattered through them, and how harvesting, hazards, encounters, and territory control all plug into the same open ground. Guide #24 (Encounters & Hazards) already owns the deep mechanics of environmental hazards and the wilderness-anomaly event loop — this guide points there rather than repeating it. Guide #11 (Territory Control) owns the full faction-claim economy the same way.

If you only have ten minutes, read **§1 What the Wilderness Is** and **§4 The Four Regions**. That's enough to walk out into the sand with your eyes open. The rest covers the landmark roster, harvesting, and how the wild connects to the rest of the game.

---

## 1. What the Wilderness Is

City-map rooms are **content-dense** — every room is hand-authored, every exit leads somewhere specific. Wilderness regions are the opposite: **content-sparse, event-dense**. Most tiles have no unique story attached to them — just terrain, a description drawn from a pool, and the twin suns or the dark overhead. What *does* happen out there — a Tusken war party cresting a dune, a krayt dragon's bleached ribcage half-buried in the sand, a Black Sun crawler-hideout in the Coruscant undercity — hits harder for being rare.

Mechanically, a wilderness region is a **coordinate grid** (an x/y plane, region-specific in size) rather than a network of named rooms. Your character has a position `(x, y)` inside the region instead of a single room ID. Moving a direction shifts your coordinates by one tile; `look` renders whatever's at your current tile — a terrain description, the local security and threat tags, the tiles around you, and anyone else standing at your exact spot.

**Regions also carry named landmarks** — fixed, authored sites with their own descriptions, distinct from the generic terrain around them (see §5). And every wilderness region is, by default, **Lawless** security (see [Security Zones](#/guide/security-zones)) — no Republic patrol is coming to bail you out, and PvP doesn't need mutual consent out here.

---

## 2. Getting There

You don't spawn in the wilderness — you walk into one from a specific hand-built room at the region's edge, called an **entry point**. Four regions exist today, each with its own gateway:

| Region | Entry room | Where | Enter | Return |
|---|---|---|---|---|
| The Dune Sea | Jundland Wastes – Dune Sea Edge | Tatooine, past the Jundland canyons | `east` | `west` |
| The Jundland Wastes | Jundland Wastes – Canyon Mouth | Tatooine, out from Mos Eisley | `east` | `west` |
| The Jundland Wastes | Jundland Wastes – Beggar's Canyon | Tatooine, deeper canyon approach | `deeper` | `back` |
| Coruscant Underworld | Coruscant – Southern Underground | Coruscant's lawless lower city, below Coco Town | `vent` | `climb` |
| The E'Y-Akh | Geonosis – E'Y-Akh Desert – Edge | Geonosis, past the Stalgasin hive's surface holdings | `east` | `west` |

Two of these are worth flagging. **Beggar's Canyon** is a *second*, deeper entry into the Jundland Wastes — same region, a different grid tile, reached by typing `deeper` rather than a compass word. And the Coruscant Underworld's `vent` is a **one-way drop**: there's no casual step back out. You climb out only by returning to the exact tile where you dropped in and typing `climb`.

Once you're in, `look` (or the game's automatic look after a move) shows you the region name and your coordinates, the terrain, the security and threat tags, and the tiles around you.

---

## 3. Moving Through the Open Wild

Inside a region, movement is compass-based:

```
north / south / east / west
northeast / northwest / southeast / southwest
(and their abbreviations: n, s, e, w, ne, nw, se, sw)
```

Each move shifts your coordinates by one tile and re-renders `look` automatically. There's no separate "explore" command — walking *is* exploring. `coords` (alias `coordinates`) shows your current position and the region's bounds if you just want the numbers without a full `look`.

**The `look` output tells you a lot at once.** Alongside the terrain description you'll see a security tag (`[LAWLESS]` by default, upgraded to `[CONTESTED]` for a claimed region's owning faction — see §8), the terrain's movement difficulty, an ambient-hazard hint if the ground itself is dangerous, the region's ownership/influence block if a faction has a stake in it, the terrain in each cardinal direction around you, and anyone else standing at your exact tile.

**You only see — and are seen by — people at your exact coordinates.** Two characters in the same wilderness region but different tiles are as far apart as two characters on different planets: `say`, `whisper`, combat, trading, healing, all of it is scoped to your tile, not the region as a whole. If you're trying to meet a friend out in the Dune Sea, you need to actually be standing where they are — not just "in the region."

**`+threat`** (alias `threat`) shows the area's threat band — how dangerous the local hostiles are, on a separate axis from security (Frontier → Settled → Contested Marches → Deep Wilds; see §4). **`+weather`** (aliases `+time`, `weather`) shows the local clock (Tatooine and Geonosis read in their own idiom) and any active storm — a sandstorm cuts Perception and ranged fire while it lasts.

Random encounters fire as you move — some are pure color, some put a hostile creature or raider band in front of you and drop you straight into combat (`attack <target>`, per [Ground Combat](#/guide/ground-combat)). §7 covers this, and Guide #24 owns the deep mechanics.

---

## 4. The Four Regions

| Region | Planet / Zone | Grid | Tile scale | Security | Threat band |
|---|---|---|---|---|---|
| The Dune Sea | Tatooine (`tatooine_dune_sea`) | 40 × 40 | 2 km/tile (~80 × 80 km) | Lawless | Deep Wilds |
| The Jundland Wastes | Tatooine (`tatooine_jundland`) | 20 × 20 | 1 km/tile (~20 × 20 km) | Lawless | Contested Marches |
| Coruscant Underworld | Coruscant (`coruscant_underworld`) | 40 × 40 | ~1 km/tile of corridor | Lawless | Contested Marches |
| The E'Y-Akh | Geonosis (`geonosis_ey_akh`) | 30 × 30 | 2 km/tile (~60 × 60 km) | Lawless | Deep Wilds |

**The Dune Sea.** Rolling open sand under the twin suns, broken by rocky outcrops, canyon cuts, and the rare oasis. Krayt dragon skeletons, Jawa sandcrawlers, dewback herds, and Tusken war parties are the region's signature — and somewhere deep in its dunes, reached only through the Jedi Village's own quest path, is the hidden monastery (see [The Jedi Village](#/guide/jedi-village)).

**The Jundland Wastes.** Tighter, rockier country than the Dune Sea — canyons, rocky outcrops, thin scrubland, and cave systems. Canyon womp rats, rock warts, Tusken patrols, and wrix packs make this a melee-heavy region rather than the Dune Sea's open-ground stalking predators. This is where the *Beggar's Canyon* of skyhopper-racing legend runs.

**Coruscant Underworld.** Level 1313 and below — the vertical descent the Republic stopped patrolling. Ferrocrete corridors, industrial ruin, service tunnels, and, at the bottom, a lightless zone the game itself flags as lethal. Black Sun operations, smuggler drops, refugee markets, and things that don't officially exist replace the desert's wildlife as the region's threat.

**The E'Y-Akh.** Geonosis's own dune sea — the low red desert making up most of the Stalgasin hive's surface holdings, running out to the black water of the Ebon Sea and the broken rock of the N'G'Zi badlands. Wild and mutant acklays (escaped or twisted arena stock) are the region's apex predators; the annual flood the locals talk about is real lore, not yet a live mechanic.

---

## 5. Wilderness Landmarks

Every region also carries a roster of fixed, named **landmarks** — sites with their own authored description, distinct from the generic terrain scrolling past on either side. These are the places quests, missions, bounties, and the Director's news point you toward — treat this section as a gazetteer of what's out there and why it matters, not a walking-tour checklist. Some landmark clusters interlink with each other through ordinary named exits (once you're standing at one, `look` shows the neighbor's name in the exit list — type a word from it to move there, the same way you'd move between two city rooms); others are stand-alone sites you're guided to directly by whatever story or activity anchors there. The Jedi Village's nine-room cluster, for instance, opens specifically through the Village invitation quest (see [The Jedi Village](#/guide/jedi-village)) — it isn't something you stumble on by blind wandering.

A handful of landmarks across the galaxy are **Force-resonant** — sites tied to the Jedi Village's hidden "signs" mechanic for Force-sensitive characters who haven't been formally invited yet (see Guide #18 for the full mechanic). They're marked below.

### The Dune Sea

| Landmark | Notes |
|---|---|
| **The Anchor Stones** ‡ | Three weathered pillars, older than the Republic. Tusken Raiders avoid them. The Village quest's navigation anchor. |
| **Ruined Obelisk** ‡ | A toppled, deliberately defaced monument — someone wanted part of it forgotten. |
| **Hermit's Hut** | A swept-clean dwelling with no visible occupant. Where the Village's invitation is formally delivered. |
| Outer Watch – Sand-Worn Pillars | The Village's outer perimeter — you're seen before you see them. |
| Village Gate | Sister Vitha keeps the watch and asks the one question that matters. |
| Common Square | The Village's heart; a well, a young apprentice, smoke from the Forge. |
| Council Hut | Where the elders meet, and an old recording stone waits. |
| Master's Chamber | Master Yarael Tinré's private space — a cup of water, offered. |
| Apprentice Tents | Bedrolls, washbasins, and one occupied tent. |
| The Forge | Smith Daro's domain — where the Trial of Flesh is taken. |
| Meditation Caves | Cool, quiet passages leading to a sealed door. |
| The Sealed Sanctum | Opens only during the Trial of Spirit. |

‡ Force-resonant.

### The Jundland Wastes

| Landmark | Notes |
|---|---|
| Beggar's Canyon Narrows | The tightest stretch of the racing canyon — the Stone Needle marker is visible from here. |
| Krayt Dragon Hollow | A canyon bowl floor made of one enormous, generations-dead krayt skeleton. Pearl chambers long since picked clean. |
| Tusken Watch Cliff | A high promontory covered in maintained red-ochre hand-marks, overlooking three canyon approaches. |
| **Bantha Graveyard** ‡ | A sheltered depression where generations of banthas have died — Tuskens tend the bones, and outsiders who bring weapons aren't welcomed back. |

‡ Force-resonant.

### Coruscant Underworld

| Landmark | Notes |
|---|---|
| **Forgotten Jedi Shrine** ‡ | An unlisted, half-buried alcove that people avoid without knowing why. |
| Black Sun Crawler Hideout | A converted maintenance crawler, heavily reinforced — bounty contracts on Black Sun lieutenants pass through here. |
| Abandoned Factory Dominus | A shuttered Republic-era munitions plant; smugglers use the lower bays as drop sites. |
| Uscru Entertainment District Fringe | The frayed, runoff edge of the glittering district two levels up. |
| The Reaper's Maze | The bottom level's most hostile ground. Threat tier: lethal. |
| Tier-Seven Warehouse Row | Sealed Republic-corporate warehouses; squatters have forced at least three units open. |
| Overflow Thoroughfare Market | A refugee-and-transient market along a sealed transit corridor; the fastest-turning jobs board around. |
| Sublevel Pump Station Nine | A decommissioned water-reclamation plant, now someone's guarded shelter. |
| Derelict Loading Docks | Collapsed cargo bays off Factory Dominus's old supply corridor — something's cached in the intact one. |
| Contraband Transfer Point | An off-manifest relay, neutral ground by convention rather than treaty. |
| Stripped Cargo-Lift Hub | A chamber where three gutted cargo-lift shafts meet — a staging ground for oversized loads. |
| The Ancient Pipe Market | A sprawling refugee market built inside decommissioned coolant mains. |
| The Foundation Stratum | An exposed cross-section of Coruscant's oldest construction layers, picked over by scavengers. |
| The Null Gallery | A pre-city void cut from the original bedrock. Total dark. Threat tier: lethal. |
| The Last Ward Marker | A defaced Public Works boundary post — past it, the lights stop. |
| The Collapse Gallery | A buckled sub-level where the geometry reads wrong, and something recent fed there. |
| The Shriek-Dark Sublevel | Shredder-bat roosts and worse, the last fringe before the Reaper's Maze. |
| Transit Shaft Alpha / Transit Shaft Beta | Wayfinding markers inside the grid. |
| Surface Manhole – Southern Underground | The tile where `climb` returns you to the city above. |

‡ Force-resonant.

### The E'Y-Akh

| Landmark | Notes |
|---|---|
| The Ebon Sea | Geonosis's one permanent body of standing water — and its worst hunting ground, home to a mutated acklay strain. |
| Golbah's Pit | A kilometers-wide glassed crater where a rebellious hive was bombed to silence. Still leaking. |
| Marmio Mio's Freighter | A wrecked Action IV transport ringed by merdeth shells — an information broker works out of the wreck. |
| The N'G'Zi Badlands | Shattered red rock at the desert's eastern edge — the wild acklays' hunting ground. |

---

## 6. Harvesting, Gear, and Survival

**`harvest`** pulls credits and crafting resources straight out of the wild — a Survival check at your current spot, no need to hunt down a specific node first. It carries a **30-minute cooldown per region** and a per-move chance of interrupting whatever else you're doing with an encounter, so plan a harvesting pass the way you'd plan any other trip out. If you harvest inside a region another faction owns, **15% of the credit yield routes to that faction's treasury** as the cost of working someone else's claimed ground — the resources themselves aren't taxed. See [Crafting](#/guide/crafting) for what the resources feed into, and [Territory Control](#/guide/territory-control) §5 for the full harvest-yield-by-influence-tier breakdown.

**Extreme heat is the wilderness's signature hazard** on all three desert regions (Dune Sea, Jundland Wastes, E'Y-Akh) — a periodic Stamina check that stacks Dehydration if you go in dry. Coruscant Underworld's dangers lean toward what's hunting you rather than the air you're breathing. A water canteen (or cooling unit) carried in your inventory is the standard desert kit; Guide #24 §6 owns the full hazard mechanic, mitigation items, and recovery.

**The Animal Excluder** is worth knowing about if you travel a lot: a craftable device (taught by Vek Nurren, the same survival-gear trainer behind the hazard mitigation kit) that has a real chance of turning away a creature encounter before it reaches you. Not a guarantee — a deterrent.

---

## 7. Encounters and Wilderness Anomalies

Two different systems put danger and opportunity in your path out here, and they're easy to conflate:

**Random encounters** fire automatically as you move — a percentage roll on each tile you enter, filtered by the destination's terrain. Some are flavor with no mechanical weight; some spawn real creatures and, if hostile, drop you straight into combat the instant they appear.

**Wilderness anomalies** are a separate, opt-in event layer: temporary sites — a stranded patrol, a salvage cache, a downed recon droid, a full-blown multi-phase operation — that spawn in a region and get announced over the news. You find them with `anomalies` (alias `anom`) while standing in the region, then travel to the anomaly's own anchor location and resolve it with `investigate <id>`.

Both of these — plus the full environmental-hazard mechanic referenced in §6 — are Guide #24's territory. **See [Encounters & Hazards](#/guide/encounters-hazards) §5 (Wilderness Anomalies) and §6 (Environmental Hazards) for the complete rules**, including the skill-gated party-challenge mechanic on the bigger anomaly events.

---

## 8. Contestable Wilderness: Territory and the Wild Economy

Wilderness regions aren't just terrain — they're the galaxy's **contestable ground**. Organizations build influence in a region through member presence, missions, and combat, and once a faction crosses the Foothold threshold it can claim the region outright: garrison NPCs deploy, a passive credit trickle starts, and the harvest-tax-on-outsiders economy from §6 kicks in. A claimed Lawless region is treated as Contested for the *owning* faction's own members — a small, real safety upgrade on their home ground.

**`+region`** (alias `+reg`) shows you the ownership, influence breakdown, weekly resource-quality multipliers, and any active contest for your current region (or a named one, e.g. `+region dune_sea`) — the same block that auto-appears in `look` while you're standing in a claimed area. Rival factions contest an owned region automatically once their own influence crosses the Control threshold; there's no separate declare-war command to learn.

This is genuinely optional content — you can explore, harvest, and fight in the wild without ever touching a faction's claim. **See [Territory Control](#/guide/territory-control) for the complete claiming, garrison, income, and contest system.**

---

## 9. A First Trip Out

You're standing at the Jundland Wastes - Dune Sea Edge, canteen in your pack. You type `east` — the rocky terrain falls away, the horizon opens, and you're in the Dune Sea at coordinates (0, 20). `look` shows rolling dune, `[LAWLESS]`, and terrain in every direction: more dune. You start walking east, one tile at a time. A few moves in, `[ENCOUNTER]` prints — a small dewback herd, non-hostile, ambling past. You keep going.

Fifteen tiles later, the heat check catches you without water in hand — Dehydration ticks up a stack. You `drink` your canteen and it clears. A `+threat` check shows Deep Wilds — the region's top danger band — so when the next `[ENCOUNTER]` line prints a Tusken war party instead of a dewback herd, you take it seriously and either fight (`attack`) with backup or fall back toward the edge. You `harvest` once along the way for a stack of raw material and a few credits. `+weather` confirms clear skies — no sandstorm complicating things today.

That's the loop: walk, read the tile, respond to what shows up, keep an eye on your water. The named landmarks and the deeper Village path are their own separate trip, opened by quests and events rather than by this kind of open walking.

---

## 10. Common Pitfalls

**1. Walking into the Dune Sea or E'Y-Akh with no water.** Extreme heat is the default state of three of the four regions. Craft or buy a canteen before you go — see Guide #24.

**2. Forgetting co-location.** If you can't find a friend "in the Dune Sea," you're probably not on their tile. `coords` and compare notes.

**3. Treating `look <direction>`, `landmarks`, or `travel <landmark>` as real commands.** They aren't. Movement is compass words, `look` renders where you are, and named landmarks are reached through the quests and events that anchor them — not through a dedicated wilderness-travel verb.

**4. Getting stuck on a one-way drop.** The Coruscant Underworld's `vent` entry only reverses at the exact tile you landed on. Don't wander far from (or lose track of) the way back before you're ready to climb out.

**5. Assuming a claimed region is safe for everyone.** The citadel security upgrade only protects the *owning* faction's own members — everyone else is still standing in Lawless (or worse, mid-contest) ground.

---

## Numbers At A Glance

| Quantity | Value |
|---|---|
| Wilderness regions live today | 4 (Dune Sea, Jundland Wastes, Coruscant Underworld, E'Y-Akh) |
| Dune Sea grid / tile scale | 40 × 40 tiles, 2 km/tile (~80 × 80 km) |
| Jundland Wastes grid / tile scale | 20 × 20 tiles, 1 km/tile (~20 × 20 km) |
| Coruscant Underworld grid / tile scale | 40 × 40 tiles, ~1 km/tile of corridor |
| E'Y-Akh grid / tile scale | 30 × 30 tiles, 2 km/tile (~60 × 60 km) |
| Default region security | Lawless (all four regions) |
| Threat bands present | Contested Marches (Jundland, Coruscant Underworld) · Deep Wilds (Dune Sea, E'Y-Akh) |
| Landmark count | Dune Sea 12 · Jundland Wastes 3 (+1 Force-resonant site) · Coruscant Underworld 20 · E'Y-Akh 4 |
| Encounter roll per tile move | 4% (Dune Sea) / 5% (Jundland Wastes, Coruscant Underworld, E'Y-Akh) |
| Per-character encounter cooldown | 60 seconds |
| Animal Excluder avert chance | 50% |
| Harvest cooldown | 30 minutes per region |
| Outsider harvest tax (non-owner faction) | 15% of credits (resources untaxed) |
| Extreme-heat hazard check | Stamina vs. Difficulty 10 base (see Guide #24) |
| Hazard check interval | 5 minutes |

---

## Commands Quick Reference

| Command | What it does |
|---|---|
| `north` / `south` / `east` / `west` / `northeast` / `northwest` / `southeast` / `southwest` (or `n`/`s`/`e`/`w`/`ne`/`nw`/`se`/`sw`) | Move one tile in the coordinate grid |
| `look` | Render your current tile — terrain, security/threat tags, surrounding terrain, anyone else present |
| `coords` (alias `coordinates`) | Show your current wilderness coordinates and the region's bounds |
| `+region [slug]` (alias `+reg`) | Show ownership, influence, resource quality, and any active contest for a region |
| `+threat` (alias `threat`) | Show the local threat band |
| `+weather` (aliases `+time`, `weather`) | Show local time-of-day and any active storm |
| `harvest` | Gather wilderness resources at your current location (30-min cooldown) |
| `anomalies` (alias `anom`) | List active wilderness anomalies in your current region — see Guide #24 |
| `investigate <id>` | Act on a wilderness anomaly at its anchor site — see Guide #24 |
| `attack <target>` | Engage a hostile encounter or creature — see Guide #3 |
| `faction claim` / `faction unclaim` / `faction territory` | Claim, release, or review your org's wilderness holdings — see Guide #11 |

---

*See also: [Encounters & Hazards](#/guide/encounters-hazards), [Security Zones](#/guide/security-zones), [Territory Control](#/guide/territory-control), [The Jedi Village](#/guide/jedi-village), [Ground Combat](#/guide/ground-combat), [Crafting](#/guide/crafting).*
