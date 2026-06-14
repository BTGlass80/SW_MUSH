---
category: economy
order: 2
summary: "Mining, resources, recipes, and turning raw materials into weapons, armor, gear, and ships."
tags: ["crafting", "mining", "resources", "recipes", "build", "manufacture"]
---

# Crafting System

**SW_MUSH — Star Wars D6 Revised & Expanded**
**BTGlass80 — April 2026**
**Guide Version 1.0**

---

## 1. Overview

The crafting system is an SWG-lite pipeline inspired by Star Wars Galaxies. The loop is: **survey for resources → gather materials → learn schematics from NPCs → craft items → optionally experiment to improve them → teach schematics to other players.**

Crafting produces weapons, consumables (medpacs, stimpacks), and ship components. Crafted items have a **quality rating** (1–100) that determines their stats — a masterwork blaster pistol from a skilled crafter with excellent materials outperforms a store-bought one.

---

## 2. Resources

Six resource types exist in the game:

| Resource | Found In | Used For |
|----------|----------|----------|
| **Metal** | Outdoor zones (Jundland Wastes, outskirts) | Weapons, ship components, armor |
| **Chemical** | City zones (Mos Eisley, markets) | Consumables, explosives |
| **Organic** | Outdoor zones | Consumables, medical supplies |
| **Energy** | City zones | Weapons, ship components |
| **Composite** | Various | Advanced weapons, armor |
| **Rare** | Lawless zones (primarily) | High-end ship components, countermeasures |

**Surveying for resources:**
```
survey                    — Search for resources in your current zone
```

The survey command rolls a **Search** skill check. The result determines both the resource type (based on your zone) and the **quality** (1–100). Outdoor zones yield higher base quality (60–90) than city zones (30–60). Higher skill check margins improve quality further (+2 quality per margin point).

**Resource stacks** merge automatically when the same type and quality is within 5 points. When stacks merge, the quality is averaged (weighted by quantity).

**Viewing your resources:**
```
resources                 — Show your resource inventory
```

---

## 3. Schematics

You must learn a schematic before you can craft that item. **20 schematics** are available across four categories:

**Weapons (8)** — Taught by **Kayson** at the Weapon Shop:

| Schematic | Skill | Difficulty | Components | Output |
|-----------|-------|-----------|------------|--------|
| Blaster Pistol (Basic) | Blaster Repair | 12 | 2 metal, 1 energy | Blaster Pistol (4D) |
| Sporting Blaster | Blaster Repair | 14 | 2 metal, 1 energy, 1 composite | Sporting Blaster (3D+1) |
| Hold-Out Blaster | Blaster Repair | 13 | 1 metal, 1 energy, 1 composite | Hold-Out Blaster (3D+1) |
| Blaster Rifle | Blaster Repair | 16 | 3 metal, 2 energy, 1 composite | Blaster Rifle (5D) |
| Blaster Carbine | Blaster Repair | 17 | 3 metal, 2 energy, 2 composite | Blaster Carbine (5D) |
| Stun Pistol | Blaster Repair | 15 | 2 metal, 2 energy, 1 chemical | Stun Pistol |
| Vibroblade | Melee Combat | 11 | 2 metal, 1 composite | Vibroblade (STR+3D) |
| Heavy Vibroblade | Melee Combat | 14 | 3 metal, 2 composite | Vibroaxe (STR+3D+1) |

**Consumables (3)** — Taught by **Heist** at the Clinic:

| Schematic | Skill | Difficulty | Components | Output |
|-----------|-------|-----------|------------|--------|
| Medpac (Basic) | First Aid | 10 | 2 chemical, 1 organic | Medpac |
| Medpac (Advanced) | Medicine | 14 | 3 chemical, 2 organic, 1 rare | Advanced Medpac |
| Field Stimpack | First Aid | 11 | 2 chemical, 1 organic | Stimpack |

**Ship Components (7)** — Taught by **Venn Kator** at Docking Bay 94 (Tatooine) and **Renna Dox** (Nar Shaddaa):

| Schematic | Skill | Difficulty | Stat Boosted | Components |
|-----------|-------|-----------|-------------|------------|
| Engine Booster | ST Repair | 16 | Speed +1 | 4 metal, 3 energy |
| Shield Generator Mk.II | ST Repair | 18 | Shields +1 | 3 metal, 4 energy, 1 rare |
| Durasteel Armor | ST Repair | 14 | Hull +1 | 6 metal, 2 composite |
| Enhanced Sensors | ST Repair | 16 | Sensors +1 | 3 energy, 1 rare |
| Maneuvering Thrusters | ST Repair | 18 | Maneuverability +1 | 3 metal, 3 energy, 1 composite |
| Weapon FC Upgrade | Weapon Repair | 18 | Fire Control +1 | 2 energy, 1 rare |
| Hyperdrive Tuning | ST Repair | 20 | Hyperdrive +1 | 4 energy, 2 rare |

**Countermeasures (2)** — Taught by **Renna Dox** (Nar Shaddaa):

| Schematic | Skill | Difficulty | Effect | Components |
|-----------|-------|-----------|--------|------------|
| Sensor Mask | Comp Prog | 22 | Stealth +6 | 3 electronic, 2 rare |
| Comm Jammer | Comp Prog | 24 | Comm Jam +3 | 4 electronic, 3 rare |

**Learning schematics:** Talk to the appropriate trainer NPC. They'll teach you schematics relevant to their specialty. Each schematic has minimum quality requirements on its components — you need quality ≥25–70 materials depending on the recipe.

**Viewing your schematics:**
```
schematics                — List all schematics you know
```

---

## 4. Assembly (Crafting)

The `craft` command consumes required resources and rolls a skill check against the schematic's difficulty:

```
craft <schematic>         — Craft an item from a known schematic
```

**Outcomes:**

| Result | Condition | Effect |
|--------|-----------|--------|
| **Critical Success** | Wild Die exploded + succeeded | Quality ×1.5. Crafter name stamped. |
| **Success** | Roll ≥ difficulty | Quality ×1.0–1.3 (scaled by margin). Crafter name stamped. |
| **Partial Success** | Missed by ≤4 | Quality ×0.5. Resources consumed. No crafter name. |
| **Failure** | Missed by >4 | Resources NOT consumed. Try again. |
| **Fumble** | Wild Die = 1 | Resources consumed. Nothing produced. |

**Quality calculation:**
1. **Base quality** = weighted average quality of consumed components
2. **Multiplier** = based on skill check result:
   - Success: 1.0 + (margin/10 × 0.3), capped at 1.3
   - Critical: ×1.5
   - Partial: ×0.5
3. **Final quality** = base × multiplier, clamped 1–100

**Quality tiers determine item stats:**

| Quality | Tier | Condition | Max Condition | Stat Bonus |
|---------|------|-----------|---------------|------------|
| 90–100 | Masterwork | 100 | 160 | Moderate combat bonus |
| 80–89 | Superior | 100 | 140 | Minor combat bonus |
| 60–79 | Good | 100 | 120 | None |
| 40–59 | Standard | 100 | 100 | None |
| 1–39 | Poor | 60 | 60 | None |

Higher max_condition means the weapon degrades slower and needs repair less often. Masterwork items with "moderate" stat bonuses are the aspirational endgame for crafters.

---

## 5. Experimentation

The `experiment` command lets you attempt to improve an already-crafted item:

```
experiment                — Attempt to improve your last crafted item
```

Experimentation is a **harder check** with higher risk but higher potential reward:
- Success: Quality improves based on margin
- **Critical success: Quality ×2.0** (the only way to create truly exceptional items)
- Failure: Quality can *decrease*
- Fumble: Item may be damaged or destroyed

This is how you create the best items in the game — craft with good materials, then experiment to push quality above 90 for Masterwork tier.

---

## 6. Teaching

Players who know a schematic can teach it to others:

```
teach <player> <schematic>  — Teach a schematic to another player
```

This spreads crafting knowledge through the player community. Both players must be in the same room. The teacher must know the schematic. The student must not already know it.

---

## 7. The Crafting Loop

The complete crafting gameplay loop:

1. **Survey** in outdoor/lawless zones for the best quality resources (Search skill check)
2. **Gather** enough materials for your recipe (check component requirements)
3. **Learn** the schematic from the appropriate trainer NPC
4. **Craft** the item (skill check vs. difficulty, quality from materials × margin)
5. **Experiment** to push quality higher (risky but rewarding)
6. **Teach** the schematic to friends to build a crafter community

The quality system creates a market incentive — a crafter with high Blaster Repair skill and access to quality 80+ metal can consistently produce Superior-tier weapons that outperform store-bought ones. Combined with the weapon durability system (condition degrades with use), there's ongoing demand for crafted replacements.

**Economic note from audit:** Currently, surveying is free (zero credit cost). The economy audit recommends adding NPC resource vendors to set a price floor. This is a known issue but doesn't affect the crafting loop itself.

---

## 8. Commands Quick Reference

| Command | Syntax | Description |
|---------|--------|-------------|
| `survey` | `survey` | Search for resources in current zone |
| `resources` | `resources` | View your resource inventory |
| `schematics` | `schematics` | List schematics you know |
| `craft` | `craft <schematic>` | Craft an item |
| `experiment` | `experiment` | Attempt to improve last crafted item |
| `teach` | `teach <player> <schematic>` | Teach a schematic to another player |

---

