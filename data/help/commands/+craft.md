---
key: +craft
title: Craft — Crafting, Surveying, Experimenting, Teaching
category: "Commands: Economy"
summary: All crafting verbs live under +craft/<switch>. Survey for resources, craft from schematics, experiment for masterwork quality, teach other players, or buy resources from an NPC vendor.
aliases: [craft, survey, experiment, exp, resources, res, schematics, schem, teach, buyresources, buyres, +buyres]
see_also: [crafting, survey, experimentation, resources, schematics, quality, economy]
tags: [economy, crafting, command]
access_level: 0
examples:
  - cmd: "+craft"
    description: "Show your resource inventory (default — /resources)."
  - cmd: "+craft/survey"
    description: "Search your current zone for resources. Rolls Search skill; yields metal/chem/organic/energy/composite/rare."
  - cmd: "survey"
    description: "Same as +craft/survey (bare alias preserved)."
  - cmd: "+craft/resources"
    description: "View your resource inventory — type, quantity, and quality per stack."
  - cmd: "resources"
    description: "Same as +craft/resources (bare alias preserved)."
  - cmd: "res"
    description: "Short form — view resources."
  - cmd: "+craft/schematics"
    description: "List the schematics you know how to craft."
  - cmd: "schematics"
    description: "Same as +craft/schematics (bare alias preserved)."
  - cmd: "schem"
    description: "Short form — list schematics."
  - cmd: "+craft/start blaster_pistol"
    description: "Craft a Blaster Pistol from your resources. Rolls skill; quality scales with margin."
  - cmd: "craft blaster_pistol"
    description: "Same as +craft/start (bare alias preserved — craft is the legacy verb)."
  - cmd: "+craft/experiment"
    description: "Attempt to improve your last-crafted item. Harder check, higher reward — critical = ×2.0 quality."
  - cmd: "experiment"
    description: "Same as +craft/experiment (bare alias preserved)."
  - cmd: "+craft/teach Jex blaster_pistol"
    description: "Teach Jex the Blaster Pistol schematic. Both of you must be in the same room; only trainers use this path."
  - cmd: "+craft/buyresources metal 10"
    description: "Buy 10 units of metal from an NPC vendor (quality 50, 15 cr each)."
  - cmd: "buyres chemical 5"
    description: "Short alias — buy 5 units of chemical."
---

All crafting verbs are switches under +craft. Bare forms
(craft, survey, resources, schematics, experiment, teach,
buyresources) still work as aliases — typing `survey` and
`+craft/survey` reach the same code. The canonical form is
+craft/<switch>; the rest of this page uses it everywhere.

See `+help crafting` for the conceptual overview of the crafting
loop. This page is the command reference.

SWITCH REFERENCE
  /resources      View your resource inventory (also: bare '+craft', res)
  /survey         Gather resources from your current zone (Search roll)
  /schematics     List the schematics you know
  /start <schem>  Craft an item (bare: craft <schem>)
  /experiment     Improve your last-crafted item (harder check, bigger reward)
  /teach <p> <s>  Teach a schematic to another player (trainers only)
  /buyresources <type> <n>   Buy resources from an NPC vendor

THE CRAFTING LOOP

  1. SURVEY        — /survey in various zones to gather materials
  2. LEARN         — NPC trainers teach you schematics (see '+help trainers')
  3. CRAFT         — /start <schematic> consumes resources, produces item
  4. EXPERIMENT    — /experiment pushes quality up for masterwork tier
  5. TEACH         — /teach <player> <schematic> spreads knowledge

This is an SWG-lite pipeline. Quality is everything — a masterwork
blaster outperforms a store-bought one by a meaningful margin.

RESOURCE TYPES (6)

  Resource    Found In              Used For
  Metal       Outdoor zones         Weapons, ship parts, armor
  Chemical    City zones            Consumables, explosives
  Organic     Outdoor zones         Consumables, medical supplies
  Energy      City zones            Weapons, ship components
  Composite   Various               Advanced weapons/armor
  Rare        Lawless zones         High-end ship components

Outdoor zones (Jundland Wastes, outskirts, mesa) yield metal/organic
with higher base quality (60–90). City zones (Mos Eisley, markets)
yield chemical/energy at 30–60 base quality. Higher Search margin
adds +2 quality per point.

/survey

Rolls your Search skill. Outcome determines:
  - Resource type (by zone — outdoor vs city)
  - Quantity (1–3 units per survey)
  - Quality (1–100 scale, based on base + margin bonus)

Resource stacks auto-merge when the same type is within 5 quality
points. Merged stacks use weighted-average quality.

SCHEMATICS (20 available)

Taught by NPC trainers in-world:
  Weapons (8)       — Kayson at the Weapon Shop
  Consumables (6)   — Medical NPCs at the clinic
  Ship Parts (4)    — Dockside mechanics
  Armor (2)         — Specialist trainer (rare)

Use /schematics to list what you know.

/start <schematic>  (aka bare `craft <schematic>`)

Consumes the required components from your resource pool (highest-
quality stacks first), rolls the schematic's crafting skill, and
produces an item with:
  - Crafter-name stamp (you)
  - Quality score (1–100 based on materials × roll result)
  - Max condition (scaled by quality tier)

Outcomes:

  Result              Condition          Effect
  Critical Success    Wild Die exploded  Quality ×1.5. Crafter stamped.
  Success             Roll ≥ difficulty  Quality ×1.0–1.3 (margin/10×0.3)
  Partial             Missed by ≤4       Quality ×0.5. No crafter stamp.
  Failure             Missed by >4       RESOURCES NOT consumed. Try again.
  Fumble              Wild Die = 1       Resources consumed, nothing made.

QUALITY TIERS

  Quality   Tier        Max Condition   Stat Bonus
  90–100    Masterwork  160             Moderate combat bonus
  80–89     Superior    140             Minor combat bonus
  60–79     Good        120             None
  40–59     Standard    100             None
  1–39      Poor        60              None

Masterwork is the aspirational endgame. The ONLY reliable path to
masterwork is /start with high-quality materials, then /experiment
on a critical success.

/experiment

Attempts to improve your LAST crafted item. Same skill check as
/start but with modified multipliers:
  - Critical: ×2.0 quality (only path to quality > 90)
  - Success: quality improves per margin
  - Failure: quality can DECREASE
  - Fumble: item may be damaged or destroyed

High risk, high reward. Don't experiment on an item you need —
experiment on the ones you want to push into Masterwork.

/teach <player> <schematic>

Trainers (NPCs flagged as teachers) call this automatically when
you purchase a lesson from them. Players can also teach each other:
  - Both must be in the same room
  - Teacher must know the schematic
  - Student must not already know it
  - Transfer is free (player-to-player) or paid (from an NPC trainer)

/buyresources <type> <quantity>

The economy-hardening floor. NPC materials vendors at mechanics /
crafting stations sell quality-50 resources at fixed prices:

  Metal        15 cr/unit
  Chemical     20 cr/unit
  Organic      10 cr/unit
  Energy       20 cr/unit
  Composite    30 cr/unit
  Rare         (not vendor-sold)

Cheaper than buying finished goods, but worse quality than surveying
yourself. The floor ensures players can always craft even if survey
rolls go badly.

COMMON WORKFLOWS

  Starting out:
    +craft/schematics             → What can I make?
    move jundland_wastes
    +craft/survey                 → Gather metal/organic
    +craft/resources              → Confirm I have what I need
    +craft/start blaster_pistol   → Make the gun

  Pushing for Masterwork:
    (craft with 90+ quality materials)
    +craft/experiment             → Roll for critical (×2.0)

  Teaching a friend:
    (same room)
    +craft/teach Jex blaster_pistol

  Emergency materials:
    +craft/buyresources metal 20  → 300 cr, quality 50

CHEAT SHEET
  +craft                = view resources (also: /resources, res)
  +craft/survey         = gather (also: survey)
  +craft/schematics     = list known (also: schematics, schem)
  +craft/start <schem>  = make item (also: craft <schem>)
  +craft/experiment     = improve last (also: experiment, exp)
  +craft/teach <p> <s>  = transfer schematic
  +craft/buyresources <t> <n>  = buy from NPC

Sources: SWG-inspired crafting model. Quality mechanics and
experimentation rules are game-original (no direct R&E equivalent —
WEG D6 doesn't have a deep crafting system). Skill rolls use
standard R&E Search/Crafting skills (R&E p.93).
