---
key: mine
title: Mine — Wildspace Cache Extraction
category: "Commands: Ships"
summary: List visible mining cache nodes in the current wildspace zone (bare), or initiate a yield run on a specific cache by ID. Must be in open space aboard a ship. No crew station required.
aliases: []
see_also: [salvage, harvest, anomalies, +ship, space, crafting]
tags: [ships, wildspace, crafting, command]
access_level: 0
examples:
  - cmd: "mine"
    description: "List all visible mining cache nodes in your current wildspace zone."
  - cmd: "mine 3"
    description: "Attempt to extract resources from mining cache node #3."
---

Extract raw resources from mining cache nodes scattered through
wildspace zones. You must be in open space (not docked). No crew
station assignment is required — anyone aboard can run a mine.

TWO FORMS

  mine          List visible mining caches in your zone.
  mine <id>     Extract from the cache with the given ID.

LISTING CACHES (bare mine)

Displays all `available` mining caches visible to your character
in the current zone. Each entry shows:
  - Cache ID (use with `mine <id>`)
  - Cache type (ore vein / gas pocket / debris field)
  - Approximate yield
  - Rep gate (if any — some caches require minimum faction rep)

Caches on cooldown (depleted, waiting to respawn) are shown
separately so you know when to return.

EXTRACTING (mine <id>)

Runs a Space Transports or Piloting skill check against a
per-cache difficulty. On success, resources are added directly
to your ship's cargo hold:

  metal, energy, composite, rare

Yield quantity and quality scale with your roll margin above DC.
A critical success extracts an extra rare resource stack.

Some caches require minimum reputation with the controlling
faction to access — listed in the cache entry.

SHIP MODS (Salvage Arm / Mining Resonator)

Certain ship mods improve mining results:
  - Mining Resonator: +pip bonus to the skill roll
  - Extended Drill:   bonus yield on success
  - Deep-Core Array:  unlocks deeper cache tiers not visible bare

Mods are installed via `+ship/install <item>`. See
`+help +ship` for the installation flow.

COOLDOWNS

Each cache node has an individual respawn timer. After a
successful harvest the node enters cooldown and is listed as
"cooling" (not "available"). Return once the timer clears.

WILDSPACE THEATERS

Mining caches are zone-specific and appear only in wildspace
zones (Hutt Frontier, Sieges Corridor, etc.). In standard
space zones `mine` returns "No cache nodes are registered for
this zone."

EXAMPLES

  (in the Hutt Frontier, aboard a YT-1300)
  mine
  → Lists: [3] Ore Vein — ~8t metal+composite  [available]
            [7] Gas Pocket — ~4t energy           [cooldown 14m]

  mine 3
  → Roll Space Transports vs DC 12 … success (margin +4)
  → +6t metal, +2t composite added to cargo hold.

CHEAT SHEET
  mine        = list visible mining caches in zone
  mine <id>   = extract from cache node <id>
  salvage     = recover from a derelict (different verb, different source)
  harvest     = faction cache nodes (same space context, different kind)
