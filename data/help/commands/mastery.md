---
key: mastery
title: Mastery — Master-Trainer Questlines
category: "Commands: Character"
summary: End-game questlines offered by master trainers in dangerous zones. Completing a questline unlocks that trainer's Tier-5 schematics. Talk to a master trainer first to be offered one.
aliases: [masteries, mastertrials]
see_also: [chain, +craft, +cpstatus, +teach, skills, advancement]
tags: [progression, crafting, tier5, questline, command]
access_level: 0
examples:
  - cmd: "mastery"
    description: "Show your active questline (or any offer from an NPC in this room)."
  - cmd: "mastery status"
    description: "Detailed status of your active questline."
  - cmd: "mastery start q-fire-3"
    description: "Begin questline q-fire-3 offered by the master trainer here."
  - cmd: "mastery abandon"
    description: "Abandon your active questline. You can restart it later."
---

Master-trainer questlines are end-game tasks that gate Tier-5 crafting
schematics. Each faction's master trainer offers their own questline —
complete it to unlock their advanced blueprint catalogue.

SYNTAX

  mastery               Show active questline or offers in this room
  mastery status        Detailed step breakdown of your active questline
  mastery start <id>    Begin an offered questline (get id from `mastery`)
  mastery abandon       Give up the active questline (can restart later)

HOW TO BEGIN

  1. Travel to the region where the master trainer is located. Master
     trainers appear in contested or lawless zones — check `+who` or
     the zone map for known NPC presences.
  2. `talk <trainer name>` — opens the NPC dialogue.
  3. The trainer will offer you a questline if you meet any prerequisites
     (typically: some crafting CP, relevant schematic tier already bought).
  4. `mastery` in the same room shows the offer with its questline id.
  5. `mastery start <id>` accepts and begins the questline.

QUESTLINE STEPS

Steps work identically to tutorial chains: most advance automatically
as you play (fight, travel, collect, complete missions). Steps that
require a skill roll use `chain attempt` — the `mastery status` output
will tell you which command to use.

  mastery status
  → Step 2 / 7: Prove your worth in the field
    Completes when: combat_won (defeat a rival crafter)
    → You must find and defeat a rival craftsperson in this zone.

You can have ONE active questline at a time. Starting a new one
requires abandoning the current.

COMPLETION REWARD

On completing the final step, the trainer's full Tier-5 schematic set
unlocks in your `+craft` panel. Some questlines also grant bonus CP,
faction reputation, or unique item rewards.

ABANDONING

`mastery abandon` returns the questline to "offered" status — you can
`mastery start <id>` it again from the same trainer at any time. Your
step progress resets to the beginning.

CHEAT SHEET

  mastery                = see active questline / room offers
  mastery start <id>     = begin offered questline
  mastery status         = step-by-step progress
  mastery abandon        = give up (restart later)
  chain attempt          = roll skill check (when step requires it)
