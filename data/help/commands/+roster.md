---
key: +roster
title: +Roster — Crew Roster
category: "Commands: Ships & Crew"
summary: View your hired NPC crew members, their station assignments, and daily wage costs.
aliases: [roster]
see_also: [+crew, +ship, +finances, +medical]
tags: [roster, crew, npc, ship, command]
access_level: 0
examples:
  - cmd: "+roster"
    description: "Show your hired crew and their station assignments."
---

Display your hired NPC crew roster: who you've hired, which
station each crew member is assigned to, their role, tier, and
daily wage. Also shows your total daily wage bill and a warning
if funds are running low.

SYNTAX

  +roster

RELATED COMMANDS

  hire <name>               Hire an NPC (cantina or spaceport)
  assign <name> <station>   Assign a crew member to a station
  unassign <name>           Remove a crew member from their station
  dismiss <name>            Permanently dismiss a crew member

STATIONS

  pilot / copilot / gunner / engineer / navigator / sensors

DAILY WAGES

  Each hired NPC draws a daily wage from your credits. The
  roster shows your total daily wage burden and how many days
  your current balance will cover. If the warning shows 3 or
  fewer days remaining, top up your credits quickly or dismiss
  crew you can't afford.

EXAMPLES

  +roster
  → Name, role, tier, station, and wage for each crew member.
  → Total daily wages and days of funding remaining.

  assign Krix gunner
  → Assigns Krix to the gunner station on your current ship.

  dismiss Marko
  → Releases Marko from your crew permanently.

SEE ALSO

  +crew      Crew management and station status.
  +ship      Current ship status.
  +finances  Credit income and expense breakdown.

CHEAT SHEET
  +roster                   show crew + wages
  assign <name> <station>   assign to station
  unassign <name>           remove from station
  dismiss <name>            permanently dismiss
