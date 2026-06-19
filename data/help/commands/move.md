---
key: move
title: Movement — Navigating Rooms and Wilderness
category: "Commands: Navigation"
summary: Move between rooms using compass directions, stairs, or wilderness traversal commands.
aliases: [north, south, east, west, up, down, ne, nw, se, sw, northeast, northwest, southeast, southwest, n, s, e, w, u, d, enter, leave]
see_also: [look, travel, coords, +where, +region]
tags: [navigation, movement, wilderness, command]
access_level: 0
examples:
  - cmd: "north"
    description: "Move north (or 'n' for short)."
  - cmd: "sw"
    description: "Move southwest."
  - cmd: "up"
    description: "Move up — useful for multi-level structures."
  - cmd: "enter"
    description: "Enter a nearby structure or vessel."
---

Move between connected rooms by typing a compass direction.

COMPASS DIRECTIONS

  north / n     south / s
  east / e      west / w
  northeast / ne   northwest / nw
  southeast / se   southwest / sw
  up / u           down / d
  enter            leave

  Type the full direction or the abbreviation. The game auto-looks
  when you arrive, showing the new room description and exits.

MOVEMENT RESTRICTIONS

  • You must be logged in with a character.
  • Binders / restraints block movement — type `escape` to try to
    break free.
  • Some rooms are locked or gated (security zones, private housing).
  • Boarding a ship uses the `board` verb, not a direction.

WILDERNESS MOVEMENT

  In wilderness regions the same direction commands apply, but the
  terrain is procedurally generated. Each move costs stamina and
  may trigger encounters. Use `look` for full tile details and
  `coords` to see your grid position.

TRAVEL SHORTCUTS

  travel <destination>    — fast-travel to a major landmark
  +where                  — show known locations in your zone

CHEAT SHEET

  n / s / e / w / ne / nw / se / sw / u / d   — move one step
  enter / leave                                — enter/leave a structure
  look                                         — describe current room
  coords                                       — show wilderness position
  escape                                       — break free of restraints
