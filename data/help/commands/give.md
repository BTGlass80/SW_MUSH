---
key: give
title: Give — Hand an Item to Another Character
category: "Commands: Social"
summary: Give a carried inventory item to another player or NPC in the same room. Use trade for credits.
aliases: [hand]
see_also: [trade, loot, +inv]
tags: [social, items, command]
access_level: 0
examples:
  - cmd: "give sealed cargo crate to Dyn"
    description: "Hand a quest item to an NPC (advances the Smuggler chain)."
  - cmd: "give medpac to Tundra"
    description: "Give a medpac to another player."
  - cmd: "hand blaster to Kessa"
    description: "Alias — same as give."
---

Hand one of your carried inventory items to another player or NPC
in the same room. The transfer is immediate.

SYNTAX

  give <item> to <player>     — hand an item to another player
  give <item> to <npc>        — hand an item to an NPC
  hand <item> to <target>     — alias for give

IMPORTANT: CREDITS USE TRADE

  You cannot give credits directly with `give`.
  Use `trade <player> <amount> credits` instead.
  Credit trades require consent and are subject to a 5% tax
  (economy sink). See `+help trade`.

QUEST HAND-OFFS

  Certain NPC quest steps require giving a specific item:
    give sealed cargo crate to Dyn
  The game resolves partial item names and NPC names.

NOTES

  Both parties must be in the same room.
  Items move from YOUR inventory to the recipient immediately.
  If the recipient's inventory is full the item stays with you.

CHEAT SHEET

  give <item> to <name>    — hand item to player or NPC
  hand <item> to <name>    — alias
