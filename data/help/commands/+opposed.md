---
key: +opposed
title: +Opposed — Opposed Skill Roll
category: "Commands: Dice"
summary: Roll your skill against an opposing dice pool to determine who wins a contested action.
aliases: [opposed, vs]
see_also: [+roll, +check, dice, difficulty, skills]
tags: [dice, d6, opposed roll, contest, command]
access_level: 0
examples:
  - cmd: "+opposed dodge 5D+1"
    description: "Roll your Dodge against an opposing pool of 5D+1."
  - cmd: "+opposed persuasion 3D"
    description: "Roll Persuasion versus a 3D opposing roll."
  - cmd: "vs blaster 4D+2"
    description: "Short alias — same as +opposed."
---

Roll your skill against an explicit opposing dice pool. Both sides
roll and the higher result wins. Use this for contests, standoffs,
and any dramatic moment where you know what the opposition can do.

SYNTAX

  +opposed <your_skill> <opposing_pool>
  opposed  <your_skill> <opposing_pool>
  vs       <your_skill> <opposing_pool>

  <your_skill>     Your character's skill by name
  <opposing_pool>  A D6 dice expression (e.g. 4D+1, 3D, 5D+2)

OUTPUT

  Three lines are shown to you:
    Your skill name + full pool
    Your roll  (individual dice + Wild Die result)
    Opponent   (opposing pool rolled)
    -> WIN by N  or  LOSE by N

  Room sees "Kira Solenne wins an opposed dodge roll!" or loses notice.

WHEN TO USE

  Opposed rolls are for declared contests: dodging a specific NPC attack
  pool, arm wrestling, competing persuasion vs. resistance, etc. When
  the opposition dice are unknown, use +check with a difficulty instead.

WILD DIE

  The Wild Die applies to YOUR roll. The opposing pool is a straight
  roll (no Wild Die). A Wild Die complication still applies.

SEE ALSO

  +roll       Freeform dice pool roll.
  +check      Roll against a static difficulty number.
  dice        Full D6 Wild Die system explanation.

EXAMPLES

  +opposed dodge 5D+1
  → Your full Dodge pool vs 5D+1 (e.g. a stormtrooper's blaster).

  +opposed persuasion 3D
  → Persuasion contest vs 3D resistance pool.

  vs sneak 4D
  → Short form — Sneak vs 4D.

CHEAT SHEET
  +opposed <skill> <Xd>   your skill vs fixed opposing pool
  vs <skill> <Xd>         short alias
