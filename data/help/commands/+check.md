---
key: +check
title: +Check — Skill Check vs Difficulty
category: "Commands: Dice"
summary: Roll a skill against a named difficulty level or a numeric target to see if you succeed.
aliases: [check]
see_also: [+roll, +opposed, difficulty, dice, skills]
tags: [dice, d6, skill check, difficulty, command]
access_level: 0
examples:
  - cmd: "+check blaster 15"
    description: "Roll Blaster vs difficulty 15 (Moderate)."
  - cmd: "+check persuasion easy"
    description: "Roll Persuasion vs the Easy difficulty (10)."
  - cmd: "+check dodge 20"
    description: "Roll Dodge vs a Difficult target of 20."
---

Roll one of your skills against a difficulty number. +check tells
you whether you succeed, and by how much. Use it for practice rolls,
environmental challenges, or out-of-combat skill contests.

SYNTAX

  +check <skill> <difficulty>
  check  <skill> <difficulty>

  <skill>      Any skill by name (partial match OK)
  <difficulty> Named level or raw number (see DIFFICULTIES below)

DIFFICULTIES

  Name              Number   Notes
  ──────────────────────────────────────────────────
  very_easy             5   Basic task, no real risk
  easy                 10   Routine for trained characters
  moderate             15   Requires focus
  difficult            20   Challenging even for experts
  very_difficult       25   Near the edge of training
  heroic               30   Legendary feat
  (numeric)          any   Provide any integer directly

OUTCOME

  SUCCESS by N    You beat the target by N.
  FAILURE by N    You fell short by N.

  Room sees a brief "Kira Solenne succeeds at a persuasion check!" or
  failure notice. Full roll breakdown is shown only to you.

WILD DIE

  The Wild Die applies: a result of 1 on the Wild Die removes it plus
  the highest other die from the total (complication). See: help dice

SEE ALSO

  +roll       Roll dice without a target number.
  +opposed    Compare two rolls against each other.
  difficulty  Full difficulty scale reference.

EXAMPLES

  +check blaster 15
  → Roll Blaster vs Moderate (15). Success by 3, Failure by 2, etc.

  +check persuasion easy
  → Roll Persuasion vs Easy (10). Good for social scene warmups.

  +check dodge 20
  → Roll Dodge vs Difficult (20). Common in environmental hazards.

CHEAT SHEET
  +check <skill> <difficulty>   skill vs number (succeed/fail + margin)
  Difficulty names: very_easy easy moderate difficult very_difficult heroic
