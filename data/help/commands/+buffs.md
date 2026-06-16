---
key: +buffs
title: +Buffs — Active Effects
category: "Commands: Character"
summary: Display your active buffs and debuffs with remaining duration and stat modifiers.
aliases: [buffs, +effects]
see_also: [+sheet, +meditate, +medical, +soak]
tags: [buffs, effects, status, character, command]
access_level: 0
examples:
  - cmd: "+buffs"
    description: "Show all active buffs and debuffs."
  - cmd: "buffs"
    description: "Alias — same as +buffs."
---

Display all active buffs and debuffs on your character, including
their stat modifiers, stack count, and time remaining.

SYNTAX

  +buffs
  buffs
  +effects

OUTPUT

  ── Active Effects ──
  ▲ Combat Stim ................ +1D STR · 4m 32s remaining
  ▼ Blinded .................... -2D PER · 1m 15s remaining

SYMBOLS

  ▲    Positive effect (buff) — green
  ▼    Negative effect (debuff) — red

FIELDS

  Name        The effect name and stack count (×N if stacked).
  Modifiers   Stat bonuses/penalties in D6 notation (e.g. +1D STR,
              -2 pip PER). "special" means the effect has no
              numeric modifier but has a gameplay rule attached.
  Duration    Time remaining. "until removed" for permanent effects
              (e.g. injuries or conditions cleared by specific actions).

COMMON BUFF SOURCES

  Stims / medpacs     Temporary STR or WND boosts (medical supplies).
  Cantina drinks      Short boosts to social skills.
  Force powers        Buffs from Enhance Attribute, etc.
  Environmental       Sandstorms, blinding, poison.
  Combat conditions   Stunned, prone, off-hand penalty, etc.

WEB CLIENT

  The HUD sidebar shows active effects with icons that update in
  real time. +buffs is the text-client equivalent.

SEE ALSO

  +sheet      Full character stats including derived attributes.
  +meditate   Recover Force Points (Force users).
  +medical    Treat wounds and conditions in the field.

EXAMPLES

  +buffs
  → Full list of active effects with time remaining.

CHEAT SHEET
  +buffs / buffs / +effects   = show all active effects
