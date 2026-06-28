---
key: move
title: Movement — Navigating Rooms and Wilderness
category: "Commands: Navigation"
summary: Move between rooms by exit name, compass direction, or the go/walk/head verbs — plus stairs and wilderness traversal.
aliases: [north, south, east, west, up, down, ne, nw, se, sw, northeast, northwest, southeast, southwest, n, s, e, w, u, d, enter, leave, go, walk, head]
see_also: [look, travel, coords, +where, +region]
tags: [navigation, movement, wilderness, command]
access_level: 0
examples:
  - cmd: "cantina"
    description: "Walk through an exit by its name — type what the room calls it."
  - cmd: "north"
    description: "Move north (or 'n' for short)."
  - cmd: "go north"
    description: "Same as 'north' — the go/walk/head prefix also works."
  - cmd: "enter"
    description: "Enter a nearby structure or vessel."
---

There are three ways to move, and you do not need to memorise which one a
room wants — they all work everywhere.

WALK BY EXIT NAME

  The simplest way: type the name of an exit the room lists. If `look`
  shows an exit called "Cantina" or "Docking Bay 94", just type:

      cantina
      bay 94

  The game matches what you type against the room's exits (a partial
  name like `bay` works if it is unambiguous), and walks you there. This
  is how most named, non-compass exits work — you do not have to map them
  to a direction.

COMPASS DIRECTIONS

  Many rooms also lay out their exits as compass points:

  north / n     south / s
  east / e      west / w
  northeast / ne   northwest / nw
  southeast / se   southwest / sw
  up / u           down / d
  enter            leave

  Type the full direction or the abbreviation.

GO / WALK / HEAD

  If reflex makes you type `go north` or `walk cantina`, that works too —
  the `go`, `walk`, and `head` prefixes route to the same movement, so
  `go <direction-or-exit>` never dead-ends.

  After any move the game auto-looks, showing the new room description
  and its exits.

ON THE WEB CLIENT

  You do not have to type at all: click an exit's chip or a direction
  button in the room panel and it walks you through (it sends the same
  move for you). Typing and clicking are interchangeable.

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

  <exit name>                                  — walk through a named exit
  n / s / e / w / ne / nw / se / sw / u / d   — move one step (compass)
  go / walk / head <dir-or-exit>              — same move, verb form
  enter / leave                                — enter/leave a structure
  look                                         — describe current room
  coords                                       — show wilderness position
  escape                                       — break free of restraints
