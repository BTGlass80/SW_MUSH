---
key: +lead
title: +Lead — Lead a Combined Action
category: "Commands: Social"
summary: Lead a combined action, rolling Command to grant your party a skill bonus on their next roll.
aliases: [lead]
see_also: [+joinlead, +roll, +check, +party]
tags: [lead, command, combined-action, group, skill]
access_level: 0
examples:
  - cmd: "+lead infiltrate the compound for Kira Tundra"
    description: "Lead an infiltration, rolling Command at Moderate (15) difficulty."
  - cmd: "+lead hold the line for Marak /diff=20"
    description: "Lead at Difficult difficulty for a larger bonus."
  - cmd: "+lead/cancel"
    description: "Cancel your current lead offer."
---

Lead a combined action using your Command skill. A successful roll
grants followers a skill bonus on their NEXT roll.

SYNTAX

  +lead <action> for <player1> [<player2>...]
  +lead <action> for <player1> [/diff=10|15|20]
  +lead/cancel

DIFFICULTY AND BONUS TABLE

  Diff 10 (Easy)       → +1D bonus to followers
  Diff 15 (Moderate)   → +2D bonus (default)
  Diff 20 (Difficult)  → +3D bonus (cap)

HOW IT WORKS

  1. You type +lead <action> for <player>.
  2. The game rolls your Command skill vs the chosen difficulty.
  3. On success, named followers receive the matching dice bonus
     applied automatically to their NEXT skill roll.
  4. The bonus expires after 60 seconds if unused.
  5. You may only have one active lead at a time. Use +lead/cancel
     to clear it early.

  All named followers must be in the same room as you.

EXAMPLES

  +lead secure the perimeter for Vex
  → Rolls your Command at Moderate (15). On success, Vex gains +2D
    to their next roll.

  +lead slice the terminal for Kira Tundra /diff=10
  → Easier roll for a +1D bonus. Good when your Command is lower.

  +joinlead
  → A follower uses this to acknowledge and join the lead. See +joinlead.

SEE ALSO

  +joinlead   Accept a lead bonus as a follower.
  +roll       Make an unmodified dice roll.
  +check      Roll a skill against a target difficulty.

CHEAT SHEET
  +lead <action> for <names>   lead at Moderate (15) → +2D
  +lead ... /diff=10           Easy → +1D
  +lead ... /diff=20           Difficult → +3D
  +lead/cancel                 cancel your current lead
