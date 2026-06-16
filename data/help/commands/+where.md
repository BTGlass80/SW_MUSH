---
key: +where
title: +Where — Player Locations
category: "Commands: Social"
summary: Show all online players grouped by their current location.
aliases: [where]
see_also: [+who, +finger, say]
tags: [social, info, location, command]
access_level: 0
examples:
  - cmd: "+where"
    description: "Show all online players and where they are."
  - cmd: "where"
    description: "Alias for +where."
---

Show all online players grouped by their current room. Useful for finding
people to RP with or checking if a location is occupied before heading there.

SYNTAX

  +where
  where

OUTPUT FORMAT

  === Where Is Everyone? ===
  Location                        Player               Idle
  ────────────────────────────── ──────────────────── ──────
  Docking Bay 47, Nar Shaddaa    Tundra Vehn            2m
                                 Kira Solenne           14m
  Cantina, Nar Shaddaa           Marko Reyes            1m
  Wilderness: Tatooine Desert    Jin-Lo Shan            8m

  3 player(s) online.

OUTPUT NOTES

  • Players in the same room are grouped under a single location line.
  • Idle time shows how long since the player last typed a command.
  • Wilderness locations show the region name.
  • Only players who have entered the game world are listed.

EXAMPLES

  +where
  → Full location list of everyone online.

CHEAT SHEET
  +where  = list all online players + their rooms
  where   = same
