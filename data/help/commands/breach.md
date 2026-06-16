---
key: breach
title: Breach — Blow Open a Sealed Obstacle
category: "Commands: Exploration"
summary: Use a breaching charge to blast open a sealed door, gate, or barrier. Requires a breaching charge in your inventory and a Demolitions skill check vs the obstacle's difficulty. The charge is consumed whether you succeed or fail.
aliases: []
see_also: [lockpick, forcedoor, craft, equip]
tags: [exploration, combat-adjacent, demolitions, command]
access_level: 0
examples:
  - cmd: "breach door"
    description: "Attempt to breach the sealed door using a breaching charge from your inventory."
  - cmd: "breach blast door"
    description: "Attempt to breach an obstacle named 'blast door'."
---

Use a **breaching charge** to blast open a sealed obstacle.
Breaching is faster and louder than lockpicking and works on
obstacles that cannot be picked.

SYNTAX

  breach <obstacle>

`<obstacle>` is the name of the breachable object in the room —
doors, gates, sealed airlocks, reinforced hatches.

REQUIREMENTS

  Breaching charge   Must have one in your inventory. Charges
                     are crafted consumables (see `craft`).
                     The charge is consumed on every attempt
                     — success or failure.
  Demolitions skill  The server rolls Demolitions vs the
                     obstacle's set difficulty.

OUTCOME

  Success    The obstacle is blown open. Room broadcast of
             detonation flavour text. Passage opens immediately.
  Failure    The obstacle holds. Charge expended. Obstacle
             is not damaged and can be attempted again (if
             you have another charge).

There is no "partial failure" — breaching is binary.

NOISE + AWARENESS

A breach is loud. The detonation is broadcast to the room and
adjacent rooms. NPCs in earshot may react. Plan accordingly
if you need to stay covert.

SAFETY NOTE

Breaching targets obstacles only — it cannot be used as an
attack on characters or droids. Use the `attack` command for
direct combat.

EXAMPLES

  breach blast door
  → BOOM — the blast door buckles and swings open.

  breach airlock
  → You fumble the placement. The charge detonates off-centre
    — the airlock holds. (Charge consumed.)

  breach door         (no charge in inventory)
  → You don't have a breaching charge.

CHEAT SHEET
  breach <target>   = blow open a sealed obstacle
                      (consumes 1 breaching charge)
  lockpick <target> = silent alternative (requires lockpick kit)
  forcedoor <name>  = Force-push technique (Jedi only)
