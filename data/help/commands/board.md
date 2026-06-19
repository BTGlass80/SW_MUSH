---
key: board
title: Board / Disembark — Enter and Leave Ships
category: "Commands: Space"
summary: Board a ship docked in the current bay, or disembark back to the docking bay.
aliases: [disembark, deboard, leave_ship, boardship, boardlink]
see_also: [+pilot, launch, land, +ship]
tags: [space, ships, travel, command]
access_level: 0
examples:
  - cmd: "board"
    description: "List ships docked in this bay."
  - cmd: "board Rusty Mynock"
    description: "Board the ship named 'Rusty Mynock'."
  - cmd: "disembark"
    description: "Leave your ship and return to the docking bay."
---

Board a ship docked in a bay, or leave a ship while it is
still docked.

BOARDING A DOCKED SHIP

  board              — list ships docked in this bay
  board <ship name>  — board the named ship

  You must be in a docking bay or landing pad. Partial name
  matching works: "board rusty" finds "Rusty Mynock".

LEAVING A SHIP

  disembark          — leave the ship (docked only)
  deboard            — alias for disembark
  leave_ship         — alias for disembark

  The ship must be docked. You cannot disembark while in space.
  On disembarking, you appear in the bay the ship is docked at.

SPACE BOARDING (hostile)

  boardship <contact#>   — establish a boarding link with an enemy
                           ship in space (pilot/copilot only)
  boardship release      — sever the boarding link
  boardship status       — show current boarding link

  Hostile boarding requires being at Close range and having the
  target in your tractor beam or stationary. See `+help +pilot`.

RELATED WORKFLOW

  1. Travel to a planet or station: `+pilot` / `hyperspace`
  2. Land at a docking bay: `land`
  3. Board: `board <ship>`
  4. Launch: `launch` (or `takeoff`)

CHEAT SHEET

  board              — list ships here
  board <name>       — board ship
  disembark          — leave ship (docked)
