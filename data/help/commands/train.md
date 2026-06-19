---
key: train
title: Train — Advance a Skill
category: "Commands: Advancement"
summary: Spend Character Points to advance a skill by one pip. Costs current dice in CP.
aliases: []
see_also: [+cpstatus, +sheet, advancement, +learn, +teach]
tags: [advancement, skills, cp, command]
access_level: 0
examples:
  - cmd: "train blaster"
    description: "Advance Blaster by one pip (e.g. 4D → 4D+1). Costs 4 CP."
  - cmd: "train space transports"
    description: "Advance a multi-word skill by name."
  - cmd: "+cpstatus"
    description: "Check your current CP balance before training."
---

Spend Character Points (CP) to permanently advance a skill by
one pip. Three pips equal one full die: 4D → 4D+1 → 4D+2 → 5D.

SYNTAX

  train <skill name>     — advance the named skill by one pip

COST (WEG R&E rule)

  Cost = total dice currently in the skill pool.

  Example: Blaster at 4D costs 4 CP per pip.
    4D → 4D+1  costs 4 CP
    4D+2 → 5D  costs 4 CP
    5D → 5D+1  costs 5 CP

  Skills start at their attribute base. A skill at attribute base
  costs the same as the attribute's dice count.

SKILL NAMES

  Skill names match your character sheet (`+sheet`). Multi-word
  skills need all words: `train space transports`.

  Common skills: blaster, dodge, melee, brawling, stealth,
  streetwise, search, persuasion, piloting, astrogation,
  space transports.

CP BALANCE

  Check your balance with `+cpstatus`. CP is earned through:
    • Passive time logged in
    • Scene completions
    • Kudos from other players
    • Director AI evaluations of quality RP

  Weekly cap: 300 ticks (1 CP = 300 ticks; ~1 CP per 10-12 days).

FORCE SKILLS

  Force attributes (Control, Sense, Alter) are NOT trained with
  the `train` command — they use the Padawan/Master `+teach` path.
  See `+help +teach` and `+help +padawan`.

CHEAT SHEET

  train <skill>    — spend CP to advance one pip
  +cpstatus        — check CP balance
  +sheet           — see all skill levels
