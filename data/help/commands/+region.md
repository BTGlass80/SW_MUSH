---
key: +region
title: +Region — Wilderness Region Info
category: "Commands: Exploration"
summary: Show ownership, influence, resource quality, and contest status for a wilderness region.
aliases: ["+reg"]
see_also: [+threat, +faction, +scene]
tags: [region, wilderness, influence, territory, command]
access_level: 0
examples:
  - cmd: "+region"
    description: "Show info for your current wilderness region."
  - cmd: "+region dune_sea"
    description: "Show info for the Dune Sea region on Tatooine."
  - cmd: "+region coruscant_underworld"
    description: "Show info for the Coruscant Underworld region."
---

Display the region info block for a wilderness area: controlling
faction, influence levels, weekly resource quality, and any active
contests for that territory.

SYNTAX

  +region
  +region <slug>

  With no arguments, shows your current region (you must be in a
  wilderness area or at its entry sentinel). With a slug, shows
  the named region regardless of where you are.

WHAT IS SHOWN

  - Region name and controlling faction
  - Influence breakdown by faction
  - Weekly resource quality (affects harvest yield)
  - Active contest status (if any faction is contesting control)

  The same block appears automatically in the `look` output
  whenever you are standing in a wilderness room.

COMMON REGION SLUGS

  dune_sea            Tatooine desert
  jundland_wastes     Tatooine badlands
  coruscant_underworld   Lower depths of Coruscant
  nar_shaddaa_sprawl  Hutt slums moon
  (others vary by world — check the look description for the slug)

EXAMPLES

  +region
  → Shows the current region where you're standing.

  +region dune_sea
  → Shows Tatooine's Dune Sea influence and resource stats
    from anywhere in the game.

SEE ALSO

  +threat    Your personal Threat level within a region.
  +faction   Your faction's standing.

CHEAT SHEET
  +region              current region info
  +region <slug>       any region by slug
