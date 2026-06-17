---
key: +padawan
title: +Padawan — View Bonded Padawan Status
category: "Commands: Padawan-Master"
summary: Master-side bond status — shows your bonded Padawan(s), their online status, bond age, and Trials progress.
aliases: [padawan]
see_also: [+master, +bond, +trials, +release, +teach, +spar]
tags: [padawan, master, bond, jedi, command]
access_level: 1
examples:
  - cmd: "+padawan"
    description: "Show all active Padawan bonds and their Trial progress."
---

Show the status of your bonded Padawan(s). Masters use this to check
Padawan presence, bond age, Weight of War sense, and Trial progress.

SYNTAX

  +padawan

WHAT IT SHOWS

  - Each Padawan's name and online/offline status.
  - Bond age (days / hours / minutes since the bond was formed).
  - Weight of War sense through the bond (tier + descriptor) for
    Force-sensitive Padawans.
  - Trials passed so far (of 5 required for knighting).

REQUIREMENTS

  - You must be a Master with at least one active Padawan bond.
  - Staff can raise your master_cap (default 1) to allow multiple
    Padawans (Council-authorized Masters).

NO ACTIVE PADAWAN?

  If you have no bonds, the command shows your current master_cap
  and reminds you to use '+bond <padawan>' when in the same room
  as a prospective Padawan to propose a bond.

EXAMPLES

  +padawan
  →  Active Padawan bond(s):
  →    Anakin Skywalker  (online, bonded 12 days ago)
  →      Through the bond: Burdened — a dull ache.
  →      Trials passed: 0 of 5

SEE ALSO

  +master     Padawan-side view of their Master.
  +bond       Propose or accept a bond.
  +trials     Full Trial progress display.
  +release    Voluntarily dissolve a bond (Master-side).
  +teach      Teach a Force power to your Padawan.
  +spar       Training spar with your Padawan.

CHEAT SHEET
  +padawan   show bonded Padawan(s) status (Master use)
