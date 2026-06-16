---
key: harvest
title: Harvest — Faction Caches (Space) or Wilderness Resources (Ground)
category: "Commands: Economy"
summary: Dual-mode verb. Aboard a ship in open space — lists or extracts faction cache nodes in the current wildspace zone. On the ground in wilderness — Survival skill check for credits and resource stacks. 30-minute per-region cooldown (ground only).
aliases: []
see_also: [mine, salvage, survival, wilderness, territory, crafting, space]
tags: [economy, wildspace, wilderness, crafting, command]
access_level: 0
examples:
  - cmd: "harvest"
    description: "(Space) List visible faction caches in your wildspace zone. (Ground) Run a Survival check to collect resources from the current wilderness region."
  - cmd: "harvest 2"
    description: "(Space only) Extract from faction cache node #2."
---

`harvest` is a dual-mode verb — what it does depends on where
you are when you type it.

SPACE MODE — faction cache nodes

Aboard a ship in open space: `harvest` lists or extracts
**faction cache** nodes in your wildspace zone. These are supply
drops, hidden munitions caches, and contraband stores maintained
by factions operating in the zone.

  harvest        List visible faction caches in the zone.
  harvest <id>   Claim the cache with the given ID.

Faction caches are different from **mining caches** (`mine`):
  - No skill check — you just reach in and pull.
  - Yield = resources + faction reputation (+rep with the
    cache's owning faction on a successful claim).
  - Rep gate: some caches require minimum faction rep to see.

Caches on cooldown appear in the listing as "cooling" with
their respawn timer.

GROUND MODE — wilderness Survival check

On foot in a wilderness room (not a city-map room):

  harvest        Roll Survival vs DC 6 to collect resources.

On success you receive:
  - Credits (scaled to zone security tier and faction influence)
  - Resource stacks (metal, organic, chemical, rare)

Quality of the resource stacks depends on how far above DC you
rolled. A Heroic margin yields top-quality stacks.

YIELD MODIFIERS (ground)

  Security tier: Contested > Lawless > Occupied (higher danger,
  better yield)
  Faction influence: a zone at Control or Dominant yields more
  than a Foothold zone.
  Turf tax: if the wilderness region is owned by a faction you
  don't belong to, 15% of the credit payout routes to that
  org's treasury automatically.

COOLDOWN (ground only)

30-minute personal cooldown per region. Harvesting the same
region twice in 30 minutes returns "You have already harvested
here recently." The cooldown is per-region — you can harvest
different wilderness regions back-to-back.

Space-mode faction caches have individual per-node respawn
timers (not a personal cooldown).

MODE RESOLUTION

The verb checks context in this order:
  1. Are you aboard a ship in open space? → space mode.
  2. Otherwise → ground mode.

If you're docked (ship present but in port), the command
falls through to ground mode and behaves like you're on foot.

EXAMPLES

  (aboard a ship in Hutt Frontier)
  harvest
  → [2] Syndicate Cache — 6t metal+composite  [available]
    [9] Black Sun Stash — 3t rare              [cooldown 22m]

  harvest 2
  → +4t metal, +2t composite recovered. +15 Hutt Syndicate rep.

  (on foot in Contested wilderness)
  harvest
  → Roll Survival 4D vs DC 6 … success (margin +8)
  → +180cr. +3t organic (quality 74). +1t rare (quality 81).
  → [Survival 4D: rolled 14 vs DC 6, margin +8]

  harvest       (30 seconds later, same region)
  → "You have already harvested here recently. (28 min remaining)"

CHEAT SHEET
  harvest        = faction cache list (space) OR Survival roll (ground)
  harvest <id>   = claim specific faction cache (space only)
  mine           = mining cache extraction (space, different kind)
  mine <id>      = claim specific mining cache
  salvage        = derelict recovery (space, skill-check yield)
