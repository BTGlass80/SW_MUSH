---
key: loot
title: Loot — Take Items from a Corpse
category: "Commands: Combat"
summary: Loot items from a defeated enemy's corpse after combat.
aliases: []
see_also: [+inv, give, sell]
tags: [combat, items, loot, command]
access_level: 0
examples:
  - cmd: "loot kessa"
    description: "Take everything from Kessa's corpse."
  - cmd: "loot trooper blaster_pistol"
    description: "Take only the blaster_pistol from a stormtrooper corpse."
---

Take items from a fallen enemy's corpse after combat.

SYNTAX

  loot <name>              — take ALL items from the named corpse
  loot <name> <item_key>   — take a specific item by key

A corpse persists in the room for several minutes after death.
The target's name (or a partial match) identifies which corpse
to loot.

MULTIPLE CORPSES

  If several corpses are in the room, loot matches the first
  whose owner-name starts with the string you type.

  loot battle   — matches "Battle Droid" if it is the only one
  loot battle blaster_pistol   — take only the blaster

ITEM KEYS

  Item keys look like "blaster_pistol" or "holdout_blaster". You can
  see a corpse's item list by looting with just the name — it will
  list items if the corpse is empty or you need a specific key.

NOTES

  You can only loot corpses in the same room as you.
  Items go directly to your inventory (check with `+inv`).
  Other players can also loot the same corpse — first-come,
  first-served.

CHEAT SHEET

  loot <name>              — take everything
  loot <name> <item_key>   — take specific item
