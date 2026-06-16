---
key: +roll
title: +Roll — Roll Dice
category: "Commands: Dice"
summary: Roll a D6 dice pool or a character skill directly, with Wild Die mechanics.
aliases: [roll]
see_also: [+check, +opposed, dice, difficulty, skills]
tags: [dice, d6, roll, command]
access_level: 0
examples:
  - cmd: "+roll 4D"
    description: "Roll 4 dice (with Wild Die)."
  - cmd: "+roll 3D+2"
    description: "Roll 3 dice and add 2 pips."
  - cmd: "+roll blaster"
    description: "Roll your Blaster skill pool."
  - cmd: "+roll dodge -1D"
    description: "Roll Dodge with a -1D situational penalty."
---

Roll a D6 dice pool or one of your character skills. All rolls
include the Wild Die — one die that can explode on a 6 or cause
a complication on a 1. Results are shown privately to you and
briefly announced to the room.

SYNTAX

  +roll <dice>            Roll a raw dice pool (e.g. 3D, 4D+2)
  +roll <skill>           Roll your full skill pool by name
  +roll <skill> +1D       Roll skill with a bonus die
  +roll <skill> -1D       Roll skill with a penalty die
  roll  ...               Alias — same as +roll

DICE NOTATION

  D6 dice pools are written as NdiceD+pips:
    4D       = four dice, no pip modifier
    3D+1     = three dice plus 1 pip
    3D+2     = three dice plus 2 pips
  Pips cycle: +2 pips + 1 pip = +1 die (every 3 pips = 1D).

SKILL ROLLS

  Provide a skill name instead of a dice expression. +roll looks up
  your current pool (attribute + skill ranks) and rolls it. Partial
  name matches work as long as they are unambiguous.

  Examples: roll blaster  |  roll dodge  |  roll persuasion

WILD DIE

  One die in every pool is the Wild Die.
    6 → Explode: add 6 and roll again (can chain repeatedly).
    1 → Complication: remove the Wild Die AND your highest die.
  The Wild Die result is shown in the roll breakdown.

MODIFIERS

  Append +ND or -ND at the end to add or remove temporary dice:
    +roll dodge -1D    — dodge pool at one-die penalty
    +roll blaster +2D  — two extra dice (e.g. aimed shot bonus)

SEE ALSO

  +check    Roll against a target difficulty number.
  +opposed  Roll your skill versus an opposing dice pool.
  help dice Full explanation of the D6 Wild Die system.

EXAMPLES

  +roll 4D
  → Raw four-die roll. Room sees your total.

  +roll blaster
  → Full Blaster skill pool (e.g. 5D if you have DEX 3D + Blaster 2D).

  +roll persuasion -1D
  → Persuasion pool minus one die (distracted, injured, etc.).

CHEAT SHEET
  +roll <dice>        raw dice pool
  +roll <skill>       character skill pool
  +roll <skill> ±ND   pool with situational modifier
