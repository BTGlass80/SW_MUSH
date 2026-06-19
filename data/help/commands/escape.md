---
key: escape
title: Escape — Break Free of Restraints
category: "Commands: Crime"
summary: Attempt to break out of binders or restraints. Requires a Strength check. One attempt per command.
aliases: [struggle]
see_also: [+pvp, +combat, forcedoor, steal]
tags: [combat, crime, restraints, command]
access_level: 0
examples:
  - cmd: "escape"
    description: "Attempt to wrench free of your binders (Hard Strength check)."
---

Attempt to break free when restrained.

USAGE

  escape     — try to break out of binders
  struggle   — alias

MECHANICS

  Each `escape` attempt rolls Strength against a fixed difficulty
  (Hard — difficulty 20). On success you are free. On failure
  nothing changes; you can try again next round.

  You cannot move, attack, or use most commands while restrained.
  Breaking free is the only way to restore full mobility.

HOW RESTRAINTS WORK

  A player or NPC with the `cuff` command can restrain you (PvP
  consent required). Restraints are removed automatically if the
  captor uses `uncuff`, or if you successfully `escape`.

CHEAT SHEET

  escape / struggle   — one Strength attempt to break binders
  +pvp                — PvP consent and restraint rules
  +combat             — full combat reference
