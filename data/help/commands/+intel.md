---
key: +intel
title: +Intel — Intelligence Reports
category: "Commands: Espionage"
summary: Compose, seal, share, and hand over intelligence reports to earn credits and faction influence.
aliases: [intel]
see_also: [+spy, +faction, +finances, +reputation]
tags: [intel, espionage, faction, report, command]
access_level: 0
examples:
  - cmd: "+intel"
    description: "List your intel reports."
  - cmd: "+intel create Hutt Movement in Sector 7"
    description: "Start a new intelligence report."
  - cmd: "+intel add Three Hutt transports observed moving south."
    description: "Add a line to your current draft."
  - cmd: "+intel seal"
    description: "Seal the draft, making it tradeable."
  - cmd: "+intel handover"
    description: "Hand a sealed report to your faction's intel handler in this room."
---

Compose intelligence reports from field observations. Sealed reports
can be handed to your faction's intel handler for credits and
territory influence, or given to other players as tradeable intel.

SYNTAX

  +intel                        List your reports
  +intel create <title>         Start a new report
  +intel add <text>             Add a line to your current draft
  +intel seal                   Seal the report (makes it tradeable)
  +intel discard                Discard your current draft
  +intel read <id>              Read a report
  +intel give <player> <id>     Give a sealed report to another player
  +intel handover [<id>]        Hand a sealed report to your faction
                                intel handler in this room

INTEL WORKFLOW

  1. Observe something interesting in the field.
  2. +intel create <title>     — open a new draft
  3. +intel add <observation>  — add each line of intel
  4. +intel seal               — finalize (cannot edit after)
  5. +intel handover           — turn in for credit + influence reward

  The payout scales with the quality and length of the report.
  Only faction intel handlers accept handovers (look for NPCs
  marked as intel contacts in faction-controlled rooms).

EXAMPLES

  +intel create Separatist Supply Cache — Ryloth Border
  → Opens a new draft with that title.

  +intel add Cache located at grid 14-N. Three crates of ion grenades.
  → Adds a line to the current draft.

  +intel seal
  → Seals the report; it now has an ID and can be traded or turned in.

  +intel give Marak 3
  → Passes sealed report #3 to Marak (must be in the same room).

  +intel handover
  → Hands your highest-priority sealed report to the intel handler
    standing in this room. Receive credits and influence.

SEE ALSO

  +spy        Active espionage — gather intel passively.
  +faction    Your faction standing and rank.
  +reputation Your reputation scores.

CHEAT SHEET
  +intel create <title>      start a draft
  +intel add <text>          add a line
  +intel seal                finalize
  +intel handover            turn in for reward
  +intel give <name> <id>    share with player
