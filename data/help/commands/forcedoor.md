---
key: forcedoor
title: Forcedoor — Break Into a Housing Room
category: "Commands: Crime"
summary: Force a housing door open with brute strength. Only possible in lawless zones. Always alerts the owner.
aliases: [breakin, force door]
see_also: [housing, steal, escape, +pvp, +region]
tags: [crime, housing, strength, command]
access_level: 0
examples:
  - cmd: "forcedoor"
    description: "Attempt to force the housing door in this room open."
---

Force open a housing door using brute strength.

USAGE

  forcedoor     — attempt to break in
  breakin       — alias

  You must be standing adjacent to a housing room exit (in the
  corridor or node with the door).

REQUIREMENTS

  • Only possible in lawless zones. Secured and contested zones
    prevent forced entry entirely.
  • Difficulty: Moderate Strength check (difficulty 15).
  • The housing owner is always notified when someone forces
    their door, regardless of success or failure.

AFTER ENTRY

  If you succeed, you enter the housing room and can interact
  with its contents (including `steal` for trophy items). The
  door does not lock behind you.

CHEAT SHEET

  forcedoor       — break through housing door (lawless only)
  steal <item>    — take a trophy item from inside
  escape          — break free of binders
