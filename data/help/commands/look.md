---
key: look
title: Look — Examine Surroundings
category: "Commands: Navigation"
summary: Look at the current room, an NPC, another player, or an object.
aliases: [l]
see_also: [+where, +who, examine]
tags: [navigation, basic, command]
access_level: 0
examples:
  - cmd: "look"
    description: "Show the full room view — description, exits, NPCs, and players."
  - cmd: "l"
    description: "Short alias for look."
  - cmd: "look bartender"
    description: "Examine an NPC in the room."
  - cmd: "look Tundra"
    description: "Examine another player's visible appearance."
---

Look at your current surroundings, or examine a specific target in
the room.

SYNTAX

  look              — show the current room
  look <target>     — examine an NPC, player, or object
  l                 — short alias

ROOM VIEW (bare look)

  Displays:
    • Room name and description
    • Environmental flavor (time of day, atmosphere)
    • Listed exits (direction → room name)
    • NPCs present with brief status
    • Players present

  The room view is also shown automatically whenever you move.

EXAMINING A TARGET

  look <npc>       — view an NPC's description and current mood
  look <player>    — see another character's appearance and equipment
  look <object>    — inspect a visible feature mentioned in the room

  Partial names work: if only one Rodian is in the room,
  "look rod" matches them.

WILDERNESS

  In open wilderness, look shows your current tile, terrain type,
  and nearby region exits rather than a named room.

CHEAT SHEET

  look / l         — the current room (and everything in it)
  look <name>      — examine a specific NPC or player
