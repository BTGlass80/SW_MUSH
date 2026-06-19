---
key: steal
title: Steal — Trophy Theft from Housing Rooms
category: "Commands: Crime"
summary: Attempt to steal a displayed trophy item from someone's housing room. Zone security determines difficulty and whether it's possible at all.
aliases: [pilfer, swipe]
see_also: [housing, pickpocket, +spy, +pvp, +region]
tags: [crime, housing, skill-check, command]
access_level: 0
examples:
  - cmd: "steal Krayt Pearl"
    description: "Attempt to steal the Krayt Pearl trophy from this housing room."
---

Steal a displayed trophy item from a housing room.

USAGE

  steal <item name>    — attempt to lift the named trophy

  You must already be inside the housing room (enter via its
  exit from the adjacent corridor or node).

ZONE RULES

  Secured zone    — impossible; the system refuses outright.
  Contested zone  — Sneak + Security check, difficulty 30.
  Lawless zone    — Sneak check only, difficulty 15.

  Failure alerts the housing owner. Success transfers the item
  to your inventory silently.

NOTES

  • Trophy items are display pieces placed by the room owner.
  • Only items flagged as trophies can be stolen this way.
  • The owner always receives an alert when theft is attempted.
  • This is distinct from `pickpocket` (credits/items from NPCs).

CHEAT SHEET

  steal <item>        — lift a housing trophy
  pickpocket <npc>    — pick credits from an NPC
  escape              — break free of binders if caught
