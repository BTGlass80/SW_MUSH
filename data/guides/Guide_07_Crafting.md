---
category: economy
order: 2
summary: "Mining, resources, recipes, and turning raw materials into weapons, armor, gear, and ships."
tags: ["crafting", "mining", "resources", "recipes", "build", "manufacture", "armor", "schematic"]
---

# Crafting System

**Parsec — WEG D6 Revised & Expanded**
**Guide Version 2.1 — updated June 2026**

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

Crafted items have a **quality rating (1–100)** determined by your materials and skill. Higher quality means better stats and longer item life — and, for weapons, armor, and stims, a real combat edge (see §5). A masterwork blaster from a skilled crafter genuinely outperforms a store-bought one.

---

## 2. Resources

### Standard Materials (7 types)

| Resource | Found In | Common Uses |
|----------|----------|-------------|
| **Metal** | Outdoor zones (`survey`) + wilderness `harvest`; vendor | Weapons, ship components, armor |
| **Chemical** | City / market zones (`survey`); vendor | Consumables, explosives, stims |
| **Organic** | Outdoor zones (`survey`); vendor | Consumables, medpacs |
| **Energy** | City zones (`survey`); vendor | Weapons, ship components |
| **Composite** | Vendor; some wilderness `harvest` | Advanced weapons, armor |
| **Rare** | Wilderness `harvest` only (lawless zones) | Ship components, countermeasures, advanced stims |
| **Electronic** | Urban / tech zones (`survey`); vendor | Espionage gear, countermeasures |

**Rare is the one standard material you cannot `survey` or buy** — it only drops from wilderness `harvest` in lawless zones (and at higher influence tiers). Everything else can be surveyed in the right zone, bought from a vendor, or both.

**Resource stacks merge automatically** when the same type has quality within 5 points. When merging, quality is averaged (weighted by quantity).

### T5 Wilderness Materials (5 types — drop-only)

These cannot be surveyed or bought. They drop from specific wilderness sources:

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
resources       — View your current resource inventory
res             — Alias for resources
```
Rolls a **Search** skill check vs. difficulty 8. Outdoor areas yield metal and organic; city, market, and tech zones yield chemical, energy, and electronic. The margin above difficulty boosts material quality (outdoor surveys run higher, roughly q60–90; city surveys q30–60).

### Buy from a Vendor (credits; standard quality 50)
```
+craft/buyresources               — Show vendor prices
+craft/buyresources <type> <qty>  — Buy resources
+craft/buyresources metal 10      — Example
```
The bare `buyres` shorthand still resolves to `+craft/buyresources`. Available in rooms with a mechanic, technician, engineer, or shipwright, or at a workshop / forge / crafting station.

Vendors sell **metal, chemical, energy, composite, and electronic** at a fixed **standard quality of 50** (metal 15 cr, organic 10 cr, chemical/energy 20 cr, electronic 25 cr, composite 30 cr per unit). **Rare and T5 materials are never sold** — you must gather those in the wild. Surveying yields better quality than buying, but costs time and a skill roll.

---

## 4. Learning Schematics

Schematics are taught by trainer NPCs. Find the right trainer, then:

```
talk <trainer>                  — Hear what a trainer teaches (first lesson free)
learn <schematic>               — Pay tuition to learn a recipe from a trainer here
schematics                      — List all schematics you know
schem                           — Alias for schematics
```

**How trainers teach:**
- `talk <trainer>` lists their curriculum. **Each trainer's first lesson is free** — they grant you their cheapest ordinary recipe on the spot ("first lesson's on the house").
- Every other recipe costs **tuition: half the schematic's base cost, minimum 50 cr.** Buy them one at a time with `learn <schematic>` while standing in the room with that trainer. Tuition is a real credit sink, paid through `adjust_credits`.
- **T5 master recipes never come free** and are gated — they require completing the trainer's questline **and** reaching the listed faction reputation before they even appear in the curriculum (see §10).

Each schematic also has its own **minimum quality requirements** on its components, set by the recipe. As a rule of thumb, component quality bands rise with the item's tier: basic recipes accept q25 material, mid-tier need q40, advanced q55, and contraband/powered gear q70 (T5 needs q75).

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
| **T5 trainers** | Wilderness quest locations | Master-tier items (see §10) |

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

| Quality | Tier | Max Condition |
|---------|------|---------------|
| 90–100 | **Masterwork** | 160 |
| 80–89 | **Superior** | 140 |
| 60–79 | **Good** | 120 |
| 40–59 | **Standard** | 100 |
| 1–39 | **Poor** | 60 |

Higher `max_condition` means the item degrades slower and needs repair less often. Masterwork items are the aspirational goal for serious crafters.

### What quality does in combat

Crafted quality is not just cosmetic — for weapons, armor, and stims it folds directly into the dice, on these bands (hard-capped to prevent power creep):

- **Weapons** — quality 70–89 adds **+1 pip of damage**, 90–100 adds **+2 pips**; below 50 is a **−1 penalty**; 50–69 matches a vendor weapon. Experimentation (§6) can add up to +1 more damage and +1 accuracy on top (combined damage cap +1D).
- **Armor** — same band for the **soak roll**: 70–89 = +1, 90–100 = +2, below 50 = −1.
- **Stims/consumables** — a tighter band: anything 70–100 gives **+1 potency**; below 50 is −1. High quality buys *reliability* of the bonus, not runaway magnitude.

So a q50 store-bought weapon is the baseline; a q90 crafted one hits harder and lasts far longer. That gap is the whole point of the crafting economy.

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

**Max 3 experiments per weapon.** Difficulty increases with each prior experiment on the same weapon (the schematic's difficulty + 5, then +5 again per prior attempt). A critical success on experimentation yields quality ×2.0 — the only path to a truly exceptional item.

---

## 7. Teaching

```
teach <player> <schematic>      — Teach a schematic to another player
```

Both players must be in the same room. You must know the schematic; the student must not already know it. **Player-to-player teaching is free** (unlike trainer tuition) — spreading crafting knowledge strengthens the crafting economy.

---

## 8. Schematic Reference

*Difficulties and components below are pinned to the live recipe data. Component minimum-quality bands rise with tier (see §4).*

### Weapons — Kayson (Weapon Shop)

*Skills vary per schematic — most are `blaster_repair` or `melee_combat`; grenades use `demolitions`.*

| Schematic | Skill | Diff | Components |
|-----------|-------|------|------------|
| Blaster Pistol (Basic) | blaster_repair | 12 | 2 metal, 1 energy |
| Hold-Out Blaster | blaster_repair | 13 | 1 metal, 1 energy, 1 composite |
| Sporting Blaster Pistol | blaster_repair | 14 | 2 metal, 1 energy, 1 composite |
| Stun Pistol | blaster_repair | 15 | 2 metal, 2 energy, 1 chemical |
| Blaster Rifle | blaster_repair | 16 | 3 metal, 2 energy, 1 composite |
| Blaster Carbine | blaster_repair | 17 | 3 metal, 2 energy, 2 composite |
| Heavy Blaster Pistol (Thunderer) | blaster_repair | 20 | 3 metal, 2 energy, 1 composite |
| Vibroblade | melee_combat | 11 | 2 metal, 1 composite |
| Heavy Vibroblade | melee_combat | 14 | 3 metal, 2 composite |
| Vibrorapier (Duelist) | melee_combat | 17 | 2 metal, 1 composite |
| Vibrodagger (Talon) | melee_combat | 14 | 2 metal, 1 composite |
| Vibro-saw | melee_combat | 12 | 3 metal, 1 composite |
| Stun Gauntlets | melee_combat | 14 | 2 metal, 1 energy, 1 composite |
| Contact Stunner | melee_combat | 14 | 2 metal, 1 energy, 1 composite |
| Blaster Pistol (DL-22) | blaster_repair | 12 | 3 metal, 2 energy, 1 composite |
| Heavy Blaster Pistol (DL-6H) | blaster_repair | 15 | 3 metal, 2 energy, 1 composite |
| Hold-out Blaster (B22) | blaster_repair | 12 | 2 metal, 1 energy, 1 composite |
| Auto-caster | missile_weapons | 12 | 3 metal, 2 composite |
| Sniper Rifle (X-45) | blaster_repair | 17 | 4 metal, 2 energy, 1 composite |
| Blaster Rifle (Firelance) | blaster_repair | 17 | 4 metal, 2 energy, 2 composite |
| Riot Gun | blaster_repair | 17 | 4 metal, 3 energy, 2 composite |
| Sevari Flash-Pistol | firearms | 16 | 2 metal, 1 chemical, 1 composite |
| Sat'skar | melee_combat | 19 | 3 metal, 2 composite |
| Coyn'skar | melee_combat | 16 | 3 metal, 2 composite |
| Incendiary Grenade | demolitions | 12 | 2 chemical, 1 rare |
| Frag Grenade | demolitions | 17 | 2 chemical, 1 rare, 1 metal |
| Stun Grenade | demolitions | 20 | 2 chemical, 1 rare, 1 metal |
| Breaching Charge | demolitions | 17 | 2 chemical, 1 metal, 1 rare |

The Breaching Charge is consumable ordnance for the `breach` verb (forcing open sealed obstacles), not a combat weapon.

### Armor — Sela Tarn (Kayson's Weapon Shop)

*Skill: `armor_repair` for all. Components are composite-primary with a metal secondary; quantity and required quality scale with difficulty.*

| Schematic | Diff | Components / Notes |
|-----------|------|--------------------|
| Koromondain Vest (Mk 45) | 12 | Light; 2 composite, 1 metal |
| Concussion Vest (CV14-B) | 12 | Light; 3 composite, 2 metal |
| Link Armor (SupraLink) | 12 | 4 composite, 2 metal; chain-link construction |
| Camo Scout Armor | 14 | Stealth-profile; 4 composite, 2 metal |
| Blast Vest (ablative) | 14 | Ablative layer; 3 composite, 2 metal |
| Flex-Armor (TY1) | 16 | Balanced mobility; 4 composite, 2 metal |
| Castaan Staad | 16 | Rigid plating; 2 composite, 1 metal |
| Riot Armor | 17 | Heavy-duty; 3 composite, 2 metal (q40+) |
| Coynite Battle Armor | 19 | Full-body; 4 composite, 2 metal |
| Ubese Raider Armor | 19 | Sealed + environment-rated; 3 composite, 2 metal |
| Loader Exo-Frame (PL-9) | 20 | Powered labor exo-suit; 5 composite, 3 metal, 1 rare (q70). Needs the **Powersuit Operation** skill to wear well |

### Consumables — Heist & Doc Vashar (The Clinic)

| Schematic | Trainer | Skill | Diff | Components |
|-----------|---------|-------|------|------------|
| Medpac (Basic) | Heist | first_aid | 10 | 2 chemical, 1 organic |
| Field Stimpack | Heist | first_aid | 11 | 2 chemical, 1 organic |
| Medpac (Advanced) | Heist | medicine | 14 | 3 chemical, 2 organic, 1 rare |
| Adrenaline Shot | Heist | medicine | 15 | 3 chemical, 2 organic |
| Focus Stim | Heist | medicine | 15 | 3 chemical, 1 organic, 1 rare |
| Combat Stim | Heist | medicine | 20 | 4 chemical, 2 organic, 2 rare |
| FastFlesh Medpac | Doc Vashar | first_aid | 18 | 3 chemical, 2 organic |

### Field Gear & Survival — Vek Nurren (Lup's General Store)

| Schematic | Skill | Diff | Components |
|-----------|-------|------|------------|
| Insulated Water Canteen | survival | 8 | 1 metal |
| Breath Mask | first_aid | 12 | 1 chemical, 1 composite |
| Personal Cooling Unit | droid_repair | 14 | 2 energy, 1 metal |
| Anti-Theft Alarm | security | 14 | 2 energy, 1 chemical |
| Animal Excluder | security | 14 | 2 electronic, 1 composite |
| Luma Flare | demolitions | 14 | 2 chemical, 1 rare |
| Radiation Shielding Suit | armor_repair | 18 | 3 composite, 1 rare |
| Stun Cuffs | security | 14 | 1 metal, 1 composite |

Stun Cuffs (binders) are consumable restraint gear for the `cuff` verb; the Luma Flare is a thrown light/attack item. Survival gear mitigates environmental hazards while carried.

### Espionage & Tools — Kayson, Renna Dox & Heist

| Schematic | Trainer | Skill | Diff | Components |
|-----------|---------|-------|------|------------|
| Comlink Bug | Kayson | security | 8 | 1 energy, 1 composite |
| Simple Lock Picker | Kayson | security | 12 | 1 metal, 1 energy |
| MechBlaze Tracking Observer | Kayson | security | 10 | 1 energy, 1 composite |
| Lectroticker | Kayson | security | 16 | 2 composite, 1 energy |
| Code Slicer | Renna Dox | computer_prog | 16 | 2 electronic, 1 rare |
| UniTech Patch | Renna Dox | computer_prog | 14 | 2 electronic, 1 energy |
| Medscanner | Heist | computer_prog | 14 | 2 electronic, 1 rare |

**Tool bonuses** (when carried, out of combat): the Code Slicer grants +1D to `security`, the UniTech Patch +1D+2 to `security`, and the Medscanner +1D to `first_aid`. Only your best single tool applies — they don't stack.

### Ship Components — Venn Kator (Docking Bay 94) & Renna Dox

| Schematic | Trainer | Skill | Diff | Notes |
|-----------|---------|-------|------|-------|
| Durasteel Armor Plating | Venn Kator | space_transports_repair | 14 | Hull +1 |
| Engine Booster (Basic) | Venn Kator | space_transports_repair | 16 | Speed +1 |
| Enhanced Sensor Suite | Venn Kator | space_transports_repair | 16 | Sensors +1 |
| Mining Laser Mk1 | Venn Kator | space_transports_repair | 16 | +2D mining; 25% cooldown reduction |
| Shield Generator Mk.II | Venn Kator | space_transports_repair | 18 | Shields +1 |
| Aftermarket Maneuvering Thrusters | Venn Kator | space_transports_repair | 18 | Maneuverability +1 |
| Weapon Fire Control Upgrade | Venn Kator | starship_weapon_repair | 18 | Fire Control +1 |
| Onboard Refinery | Venn Kator | space_transports_repair | 18 | Enables `refine` in Wildspace |
| Reinforced Salvage Arm Mk1 | Venn Kator | space_transports_repair | 16 | +2D salvage; +1 component recovery |
| Hyperdrive Tuning Kit | Venn Kator | space_transports_repair | 20 | Hyperdrive +1 |
| Mining Laser Mk2 | Venn Kator | space_transports_repair | 20 | +3D mining; 40% cooldown; deep veins; Hutt rep 25+ |
| Reinforced Salvage Arm Mk2 | Venn Kator | space_transports_repair | 20 | +3D salvage; intact extraction; Republic rep 25+ |
| Sensor Masking Array | Renna Dox | computer_prog | 22 | Stealth +6; 3 electronic, 2 rare |
| Comm Jammer | Renna Dox | computer_prog | 24 | Comm Jam +3; 4 electronic, 3 rare |

**Wildspace Mk2 mods are reputation-gated:** Mining Laser Mk2 requires Hutt Cartel reputation ≥25; Salvage Arm Mk2 requires Republic reputation ≥25.

---

## 9. Restricted Weapons — The Gundark Lane

**Gundark** operates out of the Undercity Market on Nar Shaddaa. His schematics are contraband — harder to obtain, harder to craft, and not available through legitimate channels. Find him, build trust, and he'll teach you. These recipes require **q70 materials**, and the items they produce carry a `contraband` flag that patrol boardings will sweep for.

| Schematic | Skill | Diff | Components |
|-----------|-------|------|------------|
| Disruptor Pistol | blaster_repair | 24 | 3 metal, 2 energy, 1 composite |
| Predator Rifle (EXP-7a) | blaster_repair | 26 | 4 metal, 2 energy, 1 composite |
| Anti-Vehicle Grenade | demolitions | 26 | 2 chemical, 1 rare, 1 metal |

These are high-difficulty and require high-grade materials. The payoff is weapons that fill niches unavailable in any shop.

---

## 10. T5 Master Crafting

T5 items sit at the top of the crafting tier. They require:
1. **T5 wilderness materials** (quality 75+) from specific wilderness drop sources
2. Learning from **questline-gated T5 trainers** found in wilderness locations — these recipes always cost tuition and only appear after you finish the trainer's questline **and** reach the listed faction reputation (≥50)
3. High skill (difficulties 25–28) and a mix of T5 + standard materials

| Schematic | Trainer | Location | Output | Diff |
|-----------|---------|----------|--------|------|
| Master-Crafted Lightsaber | Master Vehn Tasaal | Jundland Wastes — hidden cave | Lightsaber | 28 |
| Top-Spec Blaster Rifle | Vossk the Armorer | Nar Shaddaa fighting pits | Best-in-slot blaster | 25 |
| Master-Grade Armor | Sabra the Smith | Nar Shaddaa Warrens | Best-in-slot armor | 25 |
| Hyperdrive Surge Converter | Lieutenant Corso Venn | Geonosis forward post | Top-tier ship component | 26 |
| Mil-Spec Ion Engine Core | Chief Dax Orrin | Geonosis hive chamber | Top-tier ship component | 27 |

T5 schematics are rare, the trainers are hard to find, and the materials are gated by specific wilderness encounters. These are end-game goals.

---

## 11. The Complete Crafting Loop

1. **Gather** — `survey` in outdoor or tech zones for free materials (15-minute cooldown); `+craft/buyresources` for quick standard-quality stock; `harvest` in the wild for rare
2. **Learn** — find the right trainer NPC, `talk` for the free first lesson, then `learn <schematic>` (tuition) for the rest
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
| `learn <schematic>` | Pay tuition to learn a recipe from a trainer in the room |
| `craft <schematic>` | Craft an item (consumes materials) |
| `experiment [list\|<axis>]` | Tune an equipped crafted weapon (damage/accuracy/durability) |
| `teach <player> <schematic>` | Teach a schematic to another player (free) |
| `+craft/buyresources [<type> <qty>]` | Buy standard-quality resources from a vendor |
| `buyres` | Bare shorthand for `+craft/buyresources` |

Every crafting verb is also reachable under the canonical `+craft/<switch>` umbrella — `+craft/survey`, `+craft/resources`, `+craft/schematics`, `+craft/start <schematic>`, `+craft/experiment`, `+craft/teach`, `+craft/buyresources`. The bare forms above are preserved aliases.
