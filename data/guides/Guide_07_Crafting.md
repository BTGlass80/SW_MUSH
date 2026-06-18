---
category: economy
order: 2
summary: "Mining, resources, recipes, and turning raw materials into weapons, armor, gear, and ships."
tags: ["crafting", "mining", "resources", "recipes", "build", "manufacture", "armor", "schematic"]
---

# Crafting System

**Parsec — WEG D6 Revised & Expanded**
**Guide Version 2.0 — updated June 2026**

---

## 1. Overview

Crafting is an SWG-lite pipeline. The loop is: **gather resources → learn a schematic from an NPC trainer → craft the item → optionally experiment to push its quality higher → teach schematics to other players.**

Crafting covers a wide range of output types:
- **Weapons** — blasters, vibroblades, grenades, specialty firearms
- **Armor** — light vests to full battle plate
- **Consumables** — medpacs, stimpacks, combat stims, binders
- **Field gear** — cooling units, breath masks, tracking tools
- **Espionage equipment** — lockpicks, bugs, slicers
- **Ship components** — drive upgrades, shields, Wildspace-specific modules
- **T5 master crafts** — questline-gated items at the top of their category

Crafted items have a **quality rating (1–100)** determined by your materials and skill. Higher quality means better stats and longer weapon life. A masterwork blaster from a skilled crafter genuinely outperforms a store-bought one.

---

## 2. Resources

### Standard Materials (7 types)

These drop from the `survey` command and from `+craft/buyresources` vendors:

| Resource | Found In | Common Uses |
|----------|----------|-------------|
| **Metal** | Outdoor zones (Jundland Wastes, outskirts, desert) | Weapons, ship components, armor |
| **Chemical** | City zones (markets, commercial) | Consumables, explosives, stims |
| **Organic** | Outdoor zones | Consumables, medpacs |
| **Energy** | City zones | Weapons, ship components |
| **Composite** | Various | Advanced weapons, armor |
| **Rare** | Lawless zones (primarily) | Ship components, countermeasures |
| **Electronic** | Urban/tech zones | Espionage gear, countermeasures |

**Resource stacks merge automatically** when the same type has quality within 5 points. When merging, quality is averaged (weighted by quantity).

### T5 Wilderness Materials (5 types — drop-only)

These cannot be surveyed. They drop from specific wilderness sources:

| Material | Source |
|----------|--------|
| **kyber_shard_minor** | Force-resonant wilderness landmarks |
| **weapons_capacitor_core** | Dune Sea T2 anomaly resolution |
| **scavenged_republic_tech** | Coruscant Underworld special harvests |
| **deep_dune_iron** | Dune Sea T3 anomaly resolution |
| **composite_chitin** | Maze Predator hunts (Coruscant) |

T5 recipes require these materials at **quality 75 or higher**. Their quality is set by your performance in the dropping event, not by a weekly regional roll.

---

## 3. Gathering Resources

### Survey (free; 15-minute cooldown)
```
survey          — Search the current zone for raw materials
res             — View your current resource inventory
```
Rolls a **Search** skill check vs. difficulty 8. Outdoor areas yield metal and organic; city areas yield chemical and energy; tech/urban areas yield electronic. The margin above difficulty boosts material quality.

### Buy from a Vendor (credits; standard quality 50)
```
+craft/buyresources               — Show vendor prices
+craft/buyresources <type> <qty>  — Buy resources
+craft/buyresources metal 10      — Example
```
The bare `buyres` shorthand still resolves to `+craft/buyresources`. Available in rooms with a mechanic, engineer, or crafting station. Standard quality (50) — surveying is better for quality but costs time. Cannot buy Rare, T5, or electronic from standard vendors.

---

## 4. Learning Schematics

Talk to the appropriate trainer NPC (`talk <name>`) and select the schematic you want to learn. Each schematic has its own minimum quality requirements on components, set by the recipe.

```
schematics      — List all schematics you know
schem           — Alias for schematics
```

### Trainer Locations

| Trainer | Location | Teaches |
|---------|----------|---------|
| **Kayson** | Weapon Shop | Standard weapons, grenades, espionage tools |
| **Sela Tarn** | Kayson's Weapon Shop | Armor (all types) |
| **Heist** | The Clinic | Medpacs, stims, medscanner |
| **Doc Vashar** | The Clinic | FastFlesh medpac (advanced) |
| **Vek Nurren** | Lup's General Store | Field/survival gear, binders |
| **Venn Kator** | Docking Bay 94 (Tatooine) | Ship components, Wildspace mods |
| **Renna Dox** | Nar Shaddaa | Countermeasures, code slicer, patch kit |
| **Gundark** | Nar Shaddaa — Undercity Market | Restricted/contraband weapons |
| **T5 trainers** | Wilderness quest locations | Master-tier items (see §9) |

---

## 5. Crafting

```
craft <schematic>       — Craft an item using a schematic you know
```

You must have the required materials in your inventory (see `resources`). Materials are consumed on craft unless you fail by more than 4.

### Outcomes

| Result | Condition | Effect |
|--------|-----------|--------|
| **Critical success** | Wild Die exploded + succeeded | Quality ×1.5; crafter name stamped |
| **Success** | Roll ≥ difficulty | Quality ×1.0–1.3 (scales with margin); crafter name stamped |
| **Partial success** | Missed by ≤4 | Quality ×0.5; materials consumed; no crafter name |
| **Failure** | Missed by >4 | Materials NOT consumed; try again |
| **Fumble** | Wild Die = 1 | Materials consumed; nothing produced |

### Quality Calculation

1. **Base quality** = weighted average quality of consumed components
2. **Multiplier** = based on skill check result (1.0 to 1.3 on success; 1.5 on critical)
3. **Final quality** = base × multiplier, clamped 1–100

### Quality Tiers

| Quality | Tier | Max Condition | Stat Bonus |
|---------|------|---------------|------------|
| 90–100 | **Masterwork** | 160 | Moderate combat bonus |
| 80–89 | **Superior** | 140 | Minor combat bonus |
| 60–79 | **Good** | 120 | None |
| 40–59 | **Standard** | 100 | None |
| 1–39 | **Poor** | 60 | None |

Higher `max_condition` means the weapon degrades slower and needs repair less often. Masterwork items are the aspirational goal for serious crafters.

---

## 6. Experimentation

After crafting a weapon, you can tune it further. Experimentation is risky — failure can reduce quality, and a fumble can damage or destroy the item. Every successful experiment adds a **breakdown die** that is rolled on each combat use (risk of malfunction).

```
experiment              — Show equipped weapon status and axis choices
experiment list         — Show available axes and prior experiment history
experiment <axis>       — Experiment on the chosen axis
exp                     — Alias for experiment
```

### Experiment Axes (Weapons)

| Axis | Name | Effect | Tradeoff |
|------|------|--------|----------|
| `damage` | Galven Pattern Upgrade | Damage output ↑ | Durability ↓ |
| `accuracy` | Beam Calibration | Accuracy ↑ | Damage ↓ |
| `durability` | Reinforced Housing | Durability ↑ | None |

**Max 3 experiments per weapon.** A critical success on experimentation yields quality ×2.0 — the only path to a truly exceptional item. Difficulty increases with each prior experiment on the same weapon.

---

## 7. Teaching

```
teach <player> <schematic>      — Teach a schematic to another player
```

Both players must be in the same room. You must know the schematic; the student must not already know it. Spreading crafting knowledge strengthens the crafting economy.

---

## 8. Schematic Reference

### Weapons — Kayson (Weapon Shop)

*Skill: listed per schematic. Most are `blaster_repair` or `melee_combat`.*

| Schematic | Skill | Diff | Components |
|-----------|-------|------|------------|
| Blaster Pistol (Basic) | blaster_repair | 12 | 2 metal, 1 energy |
| Hold-Out Blaster | blaster_repair | 13 | 1 metal, 1 energy, 1 composite |
| Sporting Blaster Pistol | blaster_repair | 14 | 2 metal, 1 energy, 1 composite |
| Stun Pistol | blaster_repair | 15 | 2 metal, 2 energy, 1 chemical |
| Blaster Rifle | blaster_repair | 16 | 3 metal, 2 energy, 1 composite |
| Blaster Carbine | blaster_repair | 17 | 3 metal, 2 energy, 2 composite |
| Heavy Blaster Pistol (Thunderer) | blaster_repair | 20 | 4 metal, 2 energy, 2 composite |
| Vibroblade | melee_combat | 11 | 2 metal, 1 composite |
| Heavy Vibroblade | melee_combat | 14 | 3 metal, 2 composite |
| Vibrorapier (Duelist) | melee_combat | 17 | 2 metal, 2 composite |
| Vibrodagger (Talon) | melee_combat | 14 | 1 metal, 1 composite |
| Vibro-saw | melee_combat | 12 | 2 metal, 1 composite |
| Stun Gauntlets | blaster_repair | 14 | 1 metal, 2 energy |
| Contact Stunner | blaster_repair | 14 | 1 metal, 2 energy, 1 chemical |
| Blaster Pistol (DL-22) | blaster_repair | 12 | 2 metal, 1 energy |
| Heavy Blaster Pistol (DL-6H) | blaster_repair | 15 | 3 metal, 2 energy |
| Hold-out Blaster (B22) | blaster_repair | 12 | 1 metal, 1 energy, 1 composite |
| Auto-caster | blaster_repair | 12 | 2 metal, 1 energy |
| Sniper Rifle (X-45) | blaster_repair | 17 | 4 metal, 2 energy, 1 composite |
| Blaster Rifle (Firelance) | blaster_repair | 17 | 3 metal, 2 energy, 2 composite |
| Riot Gun | blaster_repair | 17 | 3 metal, 2 energy, 1 composite |
| Flash-Pistol (Sevari) | blaster_repair | 16 | 2 metal, 2 energy, 1 electronic |
| Sat'skar | melee_combat | 19 | 3 metal, 2 composite |
| Coyn'skar | melee_combat | 16 | 2 metal, 2 composite |
| Incendiary Grenade | demolitions | 12 | 2 chemical, 1 metal |
| Frag Grenade | demolitions | 17 | 2 metal, 2 chemical |
| Stun Grenade | demolitions | 20 | 2 metal, 3 chemical |
| Breaching Charge | demolitions | 17 | 2 chemical, 1 metal, 1 rare |

### Armor — Sela Tarn (Kayson's Weapon Shop)

*Skill: `armor_repair` for all. Components: composite + metal (quantity/quality scales with difficulty).*

| Schematic | Diff | Notes |
|-----------|------|-------|
| Koromondain Vest (Mk 45) | 12 | Light; 2 composite, 1 metal |
| Concussion Vest (CV14-B) | 12 | Light; 3 composite, 2 metal |
| Link Armor (SupraLink) | 12 | Chain-link construction |
| Camo Scout Armor | 14 | Stealth-profile; 4 composite, 2 metal |
| Blast Vest (ablative) | 14 | Ablative layer |
| Flex-Armor (TY1) | 16 | Balanced mobility |
| Castaan Staad | 16 | Rigid plating |
| Riot Armor | 17 | Heavy-duty; 3 composite, 2 metal (q40+) |
| Coynite Battle Armor | 19 | Full-body; composite + metal + rare |
| Ubese Raider Armor | 19 | Sealed + environment-rated |
| Loader Exo-Frame (PL-9) | 20 | Labor exo-suit |

### Consumables — Heist & Doc Vashar (The Clinic)

| Schematic | Trainer | Skill | Diff | Components |
|-----------|---------|-------|------|------------|
| Medpac (Basic) | Heist | first_aid | 10 | 2 chemical, 1 organic |
| Field Stimpack | Heist | first_aid | 11 | 2 chemical, 1 organic |
| Medpac (Advanced) | Heist | medicine | 14 | 3 chemical, 2 organic, 1 rare |
| Adrenaline Shot | Heist | medicine | 15 | 2 chemical, 1 organic |
| Focus Stim | Heist | medicine | 15 | 2 chemical, 1 energy |
| Combat Stim | Heist | medicine | 20 | 3 chemical, 2 organic, 1 rare |
| FastFlesh Medpac | Doc Vashar | medicine | 18 | 3 chemical, 2 organic, 1 rare |

### Field Gear & Survival — Vek Nurren (Lup's General Store)

| Schematic | Skill | Diff | Components |
|-----------|-------|------|------------|
| Insulated Water Canteen | survival | 8 | 1 composite |
| Breath Mask | survival | 12 | 1 composite, 1 chemical |
| Personal Cooling Unit | survival | 14 | 1 composite, 1 energy |
| Anti-Theft Alarm | security | 14 | 1 electronic, 1 composite |
| Animal Excluder | survival | 14 | 1 electronic, 1 composite |
| Luma Flare | survival | 14 | 1 chemical, 1 metal |
| Radiation Shielding Suit | survival | 18 | 2 composite, 1 chemical, 1 rare |
| Stun Cuffs (Binders) | security | 14 | 1 metal, 1 composite |
| Medscanner | first_aid | 14 | 1 electronic, 1 composite |

### Espionage Equipment — Kayson & Renna Dox

| Schematic | Trainer | Skill | Diff | Components |
|-----------|---------|-------|------|------------|
| Comlink Bug | Kayson | computer_prog | 8 | 1 electronic |
| Simple Lock Picker | Kayson | security | 12 | 1 metal, 1 electronic |
| MechBlaze Tracker | Kayson | computer_prog | 10 | 1 electronic, 1 composite |
| Lectroticker | Kayson | security | 16 | 2 electronic, 1 metal |
| Code Slicer | Renna Dox | computer_prog | 16 | 2 electronic, 1 composite |
| UniTech Patch | Renna Dox | computer_prog | 14 | 1 electronic, 1 chemical |

### Ship Components — Venn Kator (Docking Bay 94) & Renna Dox

| Schematic | Trainer | Skill | Diff | Notes |
|-----------|---------|-------|------|-------|
| Durasteel Armor Plating | Venn Kator | ST_repair | 14 | Hull +1 |
| Engine Booster (Basic) | Venn Kator | ST_repair | 16 | Speed +1 |
| Enhanced Sensor Suite | Venn Kator | ST_repair | 16 | Sensors +1 |
| Mining Laser Mk1 | Venn Kator | ST_repair | 16 | +2D mining; 25% cooldown reduction |
| Shield Generator Mk.II | Venn Kator | ST_repair | 18 | Shields +1 |
| Maneuvering Thrusters | Venn Kator | ST_repair | 18 | Maneuverability +1 |
| Weapon Fire Control Upgrade | Venn Kator | weapon_repair | 18 | Fire Control +1 |
| Onboard Refinery | Venn Kator | ST_repair | 18 | Enables `refine` in Wildspace |
| Reinforced Salvage Arm Mk1 | Venn Kator | ST_repair | 16 | +2D salvage; +1 component recovery |
| Hyperdrive Tuning Kit | Venn Kator | ST_repair | 20 | Hyperdrive +1 |
| Mining Laser Mk2 | Venn Kator | ST_repair | 20 | +3D mining; 40% cooldown; deep veins; Hutt rep 25+ |
| Reinforced Salvage Arm Mk2 | Venn Kator | ST_repair | 20 | +3D salvage; intact extraction; Republic rep 25+ |
| Sensor Masking Array | Renna Dox | computer_prog | 22 | Stealth +6; 3 electronic, 2 rare |
| Comm Jammer | Renna Dox | computer_prog | 24 | Comm Jam +3; 4 electronic, 3 rare |

**Wildspace Mk2 mods are reputation-gated:** Mining Laser Mk2 requires Hutt Cartel reputation ≥25; Salvage Arm Mk2 requires Republic reputation ≥25.

---

## 9. Restricted Weapons — The Gundark Lane

**Gundark** operates out of the Undercity Market on Nar Shaddaa. His schematics are contraband — harder to obtain, harder to craft, and not available through legitimate channels. Find him, build trust, and he'll teach you.

| Schematic | Skill | Diff | Components |
|-----------|-------|------|------------|
| Disruptor Pistol | blaster_repair | 24 | 3 metal, 2 energy, 2 rare, 1 electronic |
| Predator Rifle (EXP-7a) | blaster_repair | 26 | 4 metal, 2 energy, 2 rare, 2 electronic |
| Anti-Vehicle Grenade | demolitions | 26 | 2 chemical, 1 rare, 1 metal |

These are high-difficulty and require rare materials. The payoff is weapons that fill niches unavailable in any shop.

---

## 10. T5 Master Crafting

T5 items sit at the top of the crafting tier. They require:
1. **T5 wilderness materials** (quality 75+) from specific wilderness drop sources
2. Learning from **questline-gated T5 trainers** found in wilderness locations
3. High skill (difficulties 25–28) and a mix of T5 + standard materials

| Schematic | Trainer | Location | Output | Diff |
|-----------|---------|----------|--------|------|
| Master-Crafted Lightsaber | Master Vehn Tasaal | Jundland Wastes — hidden cave | Lightsaber | 28 |
| Top-Spec Blaster Rifle | Vossk the Armorer | (questline) | Best-in-slot blaster | 25 |
| Master-Grade Armor | Sabra the Smith | (questline) | Best-in-slot armor | 25 |
| Hyperdrive Surge Converter | Lieutenant Corso Venn | (questline) | Top-tier ship component | 26 |
| Mil-Spec Ion Engine Core | Chief Dax Orrin | (questline) | Top-tier ship component | 27 |

T5 schematics are rare, the trainers are hard to find, and the materials are gated by specific wilderness encounters. These are end-game goals.

---

## 11. The Complete Crafting Loop

1. **Gather** — `survey` in outdoor or tech zones for free materials (15-minute cooldown); `+craft/buyresources` for quick standard-quality stock
2. **Learn** — find the right trainer NPC and `talk` to them for the schematic
3. **Craft** — `craft <schematic>` once you have the materials
4. **Experiment** — `experiment <axis>` to push quality toward Masterwork tier (up to 3 times per weapon)
5. **Teach** — `teach <player> <schematic>` to spread knowledge and support the crafting community

The quality system creates a genuine player economy: a crafter with high Blaster Repair and quality 80+ metal can reliably produce Superior-tier weapons that outlast and outperform anything off the shelf. Combined with weapon condition degradation, there is ongoing demand for crafted replacements.

---

## 12. Commands Quick Reference

| Command | Description |
|---------|-------------|
| `survey` | Search current zone for raw materials (15-min cooldown) |
| `resources` / `res` | View your resource inventory |
| `schematics` / `schem` | List schematics you know |
| `craft <schematic>` | Craft an item (consumes materials) |
| `experiment [list\|<axis>]` | Tune an equipped crafted weapon (damage/accuracy/durability) |
| `teach <player> <schematic>` | Teach a schematic to another player |
| `+craft/buyresources [<type> <qty>]` | Buy standard-quality resources from a vendor |
| `buyres` | Bare shorthand for `+craft/buyresources` |

Every crafting verb is also reachable under the canonical `+craft/<switch>` umbrella — `+craft/survey`, `+craft/resources`, `+craft/schematics`, `+craft/start <schematic>`, `+craft/experiment`, `+craft/teach`, `+craft/buyresources`. The bare forms above are preserved aliases.
