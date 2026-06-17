---
key: +spacedock
title: Spacedock — Full Ship Repair at a Yard
category: "Commands: Ships"
summary: Pay a spacedock facility to fully restore your docked ship — including DESTROYED systems that field repair (damcon) cannot fix. +spacedock quotes the job; +spacedock repair pays and applies it.
aliases: [spacedock, "+yard", "+repairship"]
see_also: [+ship, engineer, repair, +pilot, +bridge, damcon]
tags: [ships, repair, economy, command]
access_level: 0
examples:
  - cmd: "+spacedock"
    description: "Quote the cost to fully repair your currently docked ship."
  - cmd: "+spacedock repair"
    description: "Pay the quoted cost and immediately restore all systems."
  - cmd: "spacedock"
    description: "Same as +spacedock (bare alias preserved)."
---

Pay a spacedock facility to perform a complete overhaul of your
ship. Unlike the engineer's field repair (+ship/repair / damcon),
a spacedock can fix DESTROYED systems — not just damaged ones.

TWO STEPS

  +spacedock           Quote the job — shows cost and what will be fixed
  +spacedock repair    Pay and apply the repair

Always get the quote first so you know what you're spending.

REQUIREMENTS

  - You must be ABOARD your ship (not just in the docking bay)
  - The ship must be DOCKED (not in orbit, not in a zone)
  - You must be at a location with spacedock facilities (major
    spaceports and shipyards — not every docking bay qualifies)
  - Enough credits in your wallet to cover the job

WHAT A SPACEDOCK CAN FIX

  Field repair (damcon / +ship/repair):
    - DAMAGED systems (reduced effectiveness)
    - Cannot touch DESTROYED systems

  Spacedock repair:
    - ALL damaged systems
    - ALL destroyed systems
    - Full hull restoration to max hull points

After a spacedock repair, your ship is completely restored — same
as leaving drydock after a manufacturer overhaul.

PRICING

Repair cost scales with:
  - Total damage: destroyed systems cost more than damaged ones
  - Ship size/class: capital ships cost dramatically more than fighters
  - Number of systems affected

The quote step shows you the exact credit amount before you commit.
You are never auto-charged — repair always requires explicit
`+spacedock repair` confirmation.

FINDING A SPACEDOCK

Not every docking bay has spacedock services. Look for:
  - Major spaceports on Coruscant, Nar Shaddaa, Corellia
  - Military shipyards (faction-specific access may apply)
  - Station facilities

If you're at a location without yard services, +spacedock returns
"No spacedock facilities available here." Move to a major port.

DIFFERENCE FROM FIELD REPAIR

  damcon / +ship/repair  — free / skill roll / only fixes DAMAGED
  +spacedock             — credits / instant / fixes DAMAGED + DESTROYED

After a battle where systems were destroyed (not just damaged), a
spacedock is your only option to fully restore combat capability.
The engineer can patch damaged ones, but destroyed systems need
professional drydock work.

EXAMPLES

  (aboard your ship, docked at Nar Shaddaa)
  +spacedock
  → "Spacedock quote: Your ship has 3 damaged systems (port laser,
     shields, nav) and 1 destroyed system (hyperdrive). Full repair
     cost: 4,200 credits. Use '+spacedock repair' to proceed."

  +spacedock repair
  → "Spacedock complete. All systems restored. Cost: 4,200 cr.
     Balance: 11,800 cr."

  (not docked)
  +spacedock
  → "A spacedock can only service a docked ship."

  (no credits)
  +spacedock repair
  → "Insufficient credits. You need 4,200 cr; you have 1,500."

CHEAT SHEET
  +spacedock           = get repair quote
  +spacedock repair    = pay and fix everything (including destroyed)
  +ship/repair         = free field repair (damaged systems only)
