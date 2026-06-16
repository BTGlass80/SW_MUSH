---
key: +building
title: Building — Player-Constructed Structures
category: "Commands: Cities"
summary: Construct, manage, and demolish player-built structures on city-claimed wilderness landmarks. Buildings provide storage, crafting bonuses, vendor stalls, defense, and CP benefits.
aliases: ["+bldg", "+pbuild", "bldg"]
see_also: [+city, +region, +craft, economy, territory]
tags: [cities, buildings, construction, crafting, command]
access_level: 0
examples:
  - cmd: "+building list"
    description: "List all buildings in your current room."
  - cmd: "+building construct residence"
    description: "Begin construction of a personal storage residence."
  - cmd: "+building inspect 3"
    description: "Show details for building #3 in this room."
  - cmd: "+building store 3 medpac"
    description: "Store a medpac in building #3 (must be your residence)."
  - cmd: "+building take 3 medpac"
    description: "Take a medpac from building #3."
  - cmd: "+building demolish 3"
    description: "Demolish building #3 (owner only, 25% material refund)."
  - cmd: "+building evict 3"
    description: "Evict the owner of building #3 (city mayor only, 2-day notice)."
---

Build and manage player-constructed structures on city-claimed
wilderness landmarks. Building categories serve different purposes —
storage, crafting, commerce, defense, or community advancement.

SUBCOMMANDS
  +building list                   List buildings in current room
  +building construct <category>   Start construction
  +building inspect <id>           Show building details
  +building store <id> <item>      Store an item in your residence
  +building take <id> <item>       Retrieve an item from your residence
  +building demolish <id>          Demolish (owner only, 25% refund)
  +building evict <id>             Evict a building (mayor only, 2-day notice)

BUILDING CATEGORIES

  residence          Personal storage — up to 50 items
  crafting_station   +1D bonus to crafting rolls made here
  commerce_stall     Vendor with 50/50 revenue split with the city
  garrison_annex     +2 defending NPCs for territory defense
  cultural_hall      +1 daily CP tick for citizens using the hall

REQUIREMENTS TO CONSTRUCT

  - Rank 3+ in the city's owning faction
  - Materials in inventory + enough credits
  - Landmark must have at least one free building slot
  - Force-resonant sites cannot host buildings

Construction takes 24 real-time hours from when you commit.

CONSTRUCTION COST

Each building category has material requirements (durasteel,
fabricator components, etc.) plus a credit cost. The exact amounts
depend on the city tier and current market conditions. Use
`+building construct <category>` without committing to see a cost
preview.

DEMOLITION

The owner may demolish their building at any time:
  - 25% of the original materials are refunded
  - If you later rebuild the same category on the same spot, you
    get a 10% material discount (rebuild bonus)

The city mayor can EVICT any building (non-resident structure) with
a 2-day notice period — the owner gets a warning message and time
to remove stored items.

RESIDENCES — STORAGE DETAIL

Residences hold up to 50 items. Anyone can look at the exterior,
but only you can store/take items. Items left in a residence persist
even when you're offline. If your residence is evicted, stored items
are mailed to you (lost items trigger an automated recovery).

CRAFTING STATIONS — BONUS DETAIL

When you craft at a crafting_station building, you roll one extra
die (+1D) on the craft check. This stacks with skill-based bonuses
but not with a second crafting_station in the same room — you only
get one building bonus per roll.

COMMERCE STALLS — VENDOR DETAIL

Commerce stalls act as persistent player vendors. You stock items
for sale; buyers purchase from the stall without you being online.
Revenue is split 50/50 between your wallet and the city's treasury
(city treasury funds defense costs and public building maintenance).

GARRISON ANNEXES — DEFENSE DETAIL

Garrison annexes add 2 defending NPCs to the landmark during
territory defense events. They are persistent — the NPCs respawn
after each defense event. Multiple annexes stack (2 annexes = 4
additional defenders).

CULTURAL HALLS — CP DETAIL

Citizens who spend time in a cultural hall earn an extra CP tick per
day. Only citizens of the owning city benefit — visitors do not.
Multiple cultural halls in the same room do not stack.

EXAMPLES

  (at a claimed wilderness landmark)
  +building list
  → "Buildings here: [1] Asha's Residence  [2] Crafting Post"

  +building construct commerce_stall
  → "Cost preview: 50 durasteel, 20 fabricator parts, 500 cr.
     24 hours construction time. Confirm? (yes/no)"

  +building inspect 1
  → Shows: owner, category, stored items count, condition.

  +building store 1 medpac
  → "Medpac stored in your residence."

  +building take 1 medpac
  → "Medpac retrieved from your residence."

CHEAT SHEET
  +building list                 = see buildings here
  +building construct <type>     = start building (24h)
  +building inspect <id>         = view details
  +building store/take <id> <i>  = residence storage
  +building demolish <id>        = remove (25% refund)
