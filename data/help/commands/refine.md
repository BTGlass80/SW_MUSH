---
key: refine
title: Refine — Convert Raw Resources Mid-Flight
category: "Commands: Wildspace"
summary: Refine raw harvested resources into refined materials while in open space. Requires the Onboard Refinery ship modification. Conversion rate is 2 raw to 1 refined; refined resources sell for 3x.
aliases: []
see_also: [mine, salvage, harvest, +ship, +spacedock]
tags: [wildspace, economy, crafting, command]
access_level: 0
examples:
  - cmd: "refine durasteel"
    description: "Refine all raw durasteel in your cargo hold (2:1 conversion)."
  - cmd: "refine tibanna 10"
    description: "Refine a specific quantity of raw tibanna gas."
---

Convert raw resources to refined materials using your ship's Onboard
Refinery module, while in open space.

**Syntax:**

    refine <resource_type>             — refine all of a resource type
    refine <resource_type> <quantity>  — refine a specific amount

**Requirements:**

- Must be in open space (not docked — launch first).
- Ship must have the **Onboard Refinery** modification installed.
  Install via `+ship/install`.

**Economics:**

- Conversion: **2 raw → 1 refined** (50% yield by mass).
- Refined resources **sell for 3× raw price** and feed advanced
  crafting recipes.
- Total profit from refining vs selling raw: ~50% markup per unit.

**Note:** Refinery conversion is available only for resource types
that have a defined refined variant. Use `mine` or `salvage` to
gather raw materials first.

**See also:** `mine` and `salvage` for gathering raw resources;
`harvest` for ground-side resource collection; `+spacedock` to
install ship mods.
