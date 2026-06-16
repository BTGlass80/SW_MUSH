---
key: +cpstatus
title: CPStatus — Character Point Advancement
category: "Commands: Character"
summary: View your Character Point progression — weekly tick accumulation, CP available to spend, kudos received, and your pace toward the next advancement point.
aliases: [cpstatus, cpinfo, advancement, "+cp", "+advancement"]
see_also: [+kudos, +scenebonus, +sheet, train, skills]
tags: [advancement, cp, character-points, progression, command]
access_level: 0
examples:
  - cmd: "+cpstatus"
    description: "Show your full CP advancement panel — ticks, CP available, kudos, next milestone."
  - cmd: "cpstatus"
    description: "Same as +cpstatus (bare alias preserved)."
  - cmd: "advancement"
    description: "Another alias for the status panel."
---

Track your character advancement. Character Points (CP) are earned
from roleplay participation and spent to improve skills and
attributes via the `train` command.

WHAT IS SHOWN

  Ticks (total)       — lifetime ticks accumulated
  Ticks this week     — ticks earned in the current 7-day window
  Weekly cap          — maximum ticks per week (prevents grinding)
  CP available        — unspent CPs ready to spend
  Ticks to next CP    — how many more ticks before earning another CP
  Kudos received      — kudos you've gotten this week (each = +35 ticks)
  Kudos remaining     — how many more kudos you can receive this week

The weekly cap exists so all play styles advance at similar rates —
a player who spends 20 hours in one day doesn't outpace someone who
plays 2 hours a night every day.

EARNING TICKS

Ticks come from:
  - Posing in a scene (+scene): passive tick generation while in RP
  - Scene bonus (+scenebonus): lump award for scene completions
  - Kudos (+kudos): peer-given recognition — 35 ticks per kudos,
    max 3 kudos per week received (7-day lockout per giver)
  - Mission completion: small tick bonus per mission turned in
  - Quest completion: varies by quest tier

SPENDING CP — the `train` command

  train <skill> <value>   — raise a skill (costs CP)
  train <attr> <value>    — raise an attribute (costs more CP)

Skill improvement costs scale: raising a 3D skill to 3D+1 costs 1
CP; raising 4D to 5D costs 3 CP. Attributes cost more. Check
`+help train` for the full ladder.

KUDOS AND PEER RECOGNITION

Kudos are the peer-reward layer of advancement. Another player can
give you +kudos after a great scene — it awards you 35 ticks and
costs the giver nothing. You can receive up to 3 kudos per week
(per-giver lockout: each giver can only kudos you once per 7 days).

Use +cpstatus to see how many kudos you've received this week and
how many more slots are open.

SCENEBONUS — THE SCENE COMPLETION AWARD

When you close a scene (finish a collaborative RP session), use
+scenebonus to claim a tick award scaled to your pose count. More
active participation = more ticks. See `+help +scenebonus`.

EXAMPLES

  +cpstatus
  → "Ticks: 1,240 total | 85/200 this week
     CP available: 3
     Ticks to next CP: 115
     Kudos received: 1 / 3 (2 slots open)"

CHEAT SHEET
  +cpstatus     = full advancement panel
  +kudos        = give peer kudos for RP
  +scenebonus   = claim scene completion ticks
  train         = spend CP to raise skills/attrs
