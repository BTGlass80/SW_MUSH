---
key: travel
title: "travel — Book Interplanetary Passage"
category: "Commands: Quests"
summary: Book passage to another planet during Phases 2-3 of the From Dust to Stars quest chain. Once you own a ship (Phase 4+), use launch and hyperspace instead.
aliases: [passage, bookpassage]
see_also: [+spacerquest, +pilot, +ship, +spacedock]
tags: [quests, ships, space, command]
access_level: 0
examples:
  - cmd: "travel tatooine"
    description: "Book passage to Tatooine (must be at a docking bay)."
  - cmd: "travel narshaddaa"
    description: "Book passage to Nar Shaddaa."
  - cmd: "travel"
    description: "Show available destinations (no argument)."
---

Books passage to another planet as a paying passenger. Only available
during Phases 2-3 of the **From Dust to Stars** quest chain, before
you have your own ship.

AVAILABLE DESTINATIONS

  tatooine     Mos Eisley Docking Bay — the familiar home base.
  narshaddaa   Nar Shaddaa — the Smuggler's Moon, Hutt space.
  kessel       Kessel — spice runs, hazardous work.
  corellia     Corellia — shipyards, Republic presence.

REQUIREMENTS

  - You must be at a docking bay or landing pad.
  - You must be in Phase 2 or Phase 3 of the spacer quest chain.
  - Phase 1: travel is not yet available — complete Phase 1 first.
  - Phase 4+: you have your own ship. Use `launch` and `hyperspace`.

HOW IT WORKS

Typing `travel <planet>` teleports you to the main docking bay of
the destination world after a short narrative passage. No credits
are deducted — the Hutt Cartel considers it a business expense
during this phase of your career.

Once at the destination, continue your quest objectives. When you're
done with that world, find another docking area and `travel` back.

PHASE 4+ PLAYERS

Once you complete Phase 3 and are assigned your Ghtroc 720, the
`travel` command no longer works. Use `launch` to undock your ship,
`sensors` or `plot` to set a course, and `hyperspace` to jump.
See `help +pilot` and `help +ship` for the full space-flight flow.

CHEAT SHEET
  travel                    = list available destinations
  travel tatooine           = go to Tatooine (at a docking bay)
  travel narshaddaa         = go to Nar Shaddaa
  travel kessel             = go to Kessel
  travel corellia           = go to Corellia
  +spacerquest              = check your current phase
