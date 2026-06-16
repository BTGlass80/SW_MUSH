---
key: +soak
title: +Soak — Pre-declare CP for Damage Resistance
category: "Commands: Combat"
summary: Pre-declare Character Points to add to your Strength roll to resist damage if you are hit.
aliases: [soak]
see_also: [+combat, +pvp, +buffs, +sheet]
tags: [soak, combat, character-points, damage, command]
access_level: 0
examples:
  - cmd: "+soak 3"
    description: "Pre-declare 3 CP for soak this round."
  - cmd: "soak 1"
    description: "Alias — same as +soak 1."
---

Pre-declare Character Points (CP) to spend on your Strength soak
roll if you take damage this round. CP are only spent if you are
actually hit. Maximum 5 CP per round (WEG R&E p.55).

SYNTAX

  +soak <1-5>
  soak <1-5>

  Must be used during the declaration phase of a combat round,
  alongside other declarations like dodge or parry.

WHAT HAPPENS

  When you declare soak CP and are then hit:
    1. You roll Strength + the soak bonus from your CP.
    2. If Strength roll ≥ damage total, you take no wound.
    3. The declared CP are deducted from your pool.

  If you are NOT hit, the CP are NOT spent — the declaration
  is wasted but costs you nothing.

WEG D6 RULE

  Per R&E p.55: spending 5 CP adds +1D to a Strength roll to
  resist damage. You can spend fewer CP for a smaller bonus:

    1 CP → +1 pip to Strength soak
    2 CP → +2 pips
    3 CP → +1D (3 pips = 1D in D6)
    4 CP → +1D+1
    5 CP → +1D+2  (maximum per round)

LIMITS

  • Maximum 5 CP per round.
  • You must have enough CP available — the command checks.
  • Only valid while you are in active combat.

CHARACTER POINTS

  CP are a precious resource. They can also be spent on attack and
  skill rolls, so weigh whether soak is worth the investment vs.
  boosting your attack or dodge.

  See your CP pool on +sheet.

SEE ALSO

  +combat     View current combat state.
  +buffs      Show active effects (some give Strength bonuses).
  +sheet      Check your Strength pool and CP pool.
  +pvp        Opt in to PvP combat.

EXAMPLES

  +soak 3
  → Pre-declare 3 CP. If hit, Strength roll gets +1D to resist.

  +soak 5
  → Maximum soak declaration. Adds +1D+2 to soak if you're hit.

CHEAT SHEET
  +soak <1-5>   = pre-declare CP for damage resist (used in declaration phase)
