---
key: salvage
title: Salvage — Derelict Ship Recovery
category: "Commands: Ships"
summary: Recover resources and credits from a fully-scanned derelict anomaly in your current zone. Runs a Salvage skill check; yield scales with roll margin and installed Salvage Arm mod.
aliases: []
see_also: [mine, harvest, anomalies, investigate, +ship, space, crafting]
tags: [ships, wildspace, crafting, command]
access_level: 0
examples:
  - cmd: "salvage"
    description: "Attempt to recover salvage from a fully-scanned derelict in your zone. No argument needed."
---

Recover materials from a derelict ship anomaly in your current
zone. You must be in open space (not docked) and the derelict
must have been fully scanned first. No crew station required.

PRECONDITIONS

  1. You are in open space (not docked).
  2. A `derelict` anomaly exists in your zone.
  3. That anomaly has been scanned enough times to be fully
     revealed (`resolution >= scans_needed`).

Use `anomalies` (or the wildspace scan panel) to see what's in
your zone and whether a derelict is fully resolved. Use `scan`
or `deepscan` to advance the resolution counter.

HOW SALVAGE WORKS

Running `salvage` consumes the derelict anomaly and runs a
Starship Repair or Salvage skill check (DC varies by wreck type).
On success you receive a mix of:

  metal, energy, composite, rare
  — or credits (if the wreck had liquid assets aboard)

Loot tables differ by source:
  Derelict (pre-existing wreck): broader yield, higher rare chance
  Combat wreck (recently destroyed by players): lighter yield,
  more metal/energy, lower rare chance

SALVAGE ARM MOD

The Salvage Arm ship modification improves results:
  - Bonus pips to the skill roll
  - Extra composite yield on success
  - Intact Extraction trait: recover additional whole components
    rather than raw scrap

Install via `+ship/install <item>`. See `+help +ship`.

COMBAT WRECKS

After a ship is destroyed in combat, its wreck briefly becomes a
salvageable anomaly before it despawns. Act quickly — wrecks
don't persist indefinitely.

YIELD RANGES (approximate)

  Source       Metal   Energy  Composite  Rare   Credits
  Derelict     3–8t    2–5t    1–4t       1–2t   500–2000cr
  Combat wreck 2–5t    1–3t    1–2t       0–1t   —

Exact numbers depend on roll margin, wreck tier, and Salvage Arm
bonuses. A critical success shifts all ranges up.

EXAMPLES

  (in Hutt Frontier, a derelict shows in anomalies as resolved)
  salvage
  → Roll Salvage vs DC 14 … success (margin +3)
  → +5t metal, +3t energy, +1t rare recovered.

  salvage
  → "You aren't in open space." (if docked)

  salvage
  → "No fully-scanned derelict is present in this zone." (if
     the derelict exists but needs more scans)

CHEAT SHEET
  anomalies       = list anomalies in zone + resolution state
  scan / deepscan = advance derelict resolution counter
  salvage         = recover from a fully-resolved derelict
  mine            = mining cache nodes (different verb, different source)
