---
key: coords
title: Coords — Wilderness Grid Coordinates
category: "Commands: Navigation"
summary: Show your current grid coordinates in a wilderness region. Only meaningful outside named rooms.
aliases: [coordinates]
see_also: [look, move, +region, travel]
tags: [navigation, wilderness, command]
access_level: 0
examples:
  - cmd: "coords"
    description: "Show your (X, Y) position in the current wilderness region."
---

Show your position in a wilderness region.

USAGE

  coords          — display your current (X, Y) coordinates
  coordinates     — alias

  Only works while you are inside a procedurally generated
  wilderness area (Dune Sea, Jundland Wastes, etc.). In a named
  room or ship, the command tells you you're not in wilderness.

COORDINATES

  Each wilderness region is a grid. (0, 0) is the entry point.
  Coordinates increase east (+X) and north (+Y).

  Use `look` for full tile information — terrain type, visible
  features, and available exits. `coords` is the quick bearing
  check when you're already oriented.

CHEAT SHEET

  coords         — show grid position
  look           — full tile description + exits
  +region        — overview of the region you're exploring
  travel         — fast-travel to known landmarks
