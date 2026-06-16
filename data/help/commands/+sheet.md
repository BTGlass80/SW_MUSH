---
key: +sheet
title: +Sheet — Character Sheet
category: "Commands: Info"
summary: Display your WEG D6 character sheet — attributes, skills, combat stats, Force status, and advancement info. Supports /brief, /skills, and /combat switches.
aliases: [sheet, score, stats, +score, +stats, sc]
see_also: [+inv, advancement, attributes, skills, dice]
tags: [info, character, stats, sheet, command]
access_level: 0
examples:
  - cmd: "+sheet"
    description: "Full character sheet — attributes, skills, combat, and advancement."
  - cmd: "+sheet/brief"
    description: "Condensed one-page view with attributes and key combat stats."
  - cmd: "+sheet/skills"
    description: "Skills-only view, grouped by attribute."
  - cmd: "+sheet/combat"
    description: "Combat-focused view — wound levels, soak, attack pools."
---

Display your WEG Revised & Expanded D6 character sheet.

SYNTAX

  +sheet              Full sheet (all sections)
  +sheet/brief        Condensed summary (attributes + combat)
  +sheet/skills       Skills-only view
  +sheet/combat       Combat view (wounds, soak, attack pools)

  Aliases: sheet, score, stats, +score, +stats, sc

FULL SHEET SECTIONS

  ATTRIBUTES    Six attributes (Dexterity, Knowledge, Mechanical,
                Perception, Strength, Technical) with die codes.

  SKILLS        Each attribute's specialised skills with die codes.
                Skills above the attribute base are listed; unskilled
                attributes roll at the base die code.

  COMBAT        Wound level track (Stunned / Wounded / Incapacitated /
                Mortally Wounded), current Soak, and weapon attack pools.

  ADVANCEMENT   Character Points (CP) earned, Force Points, Dark Side
                Points (if any), experience-to-spend balance, and
                current titles.

  FORCE         Force-sensitive characters see Control / Sense / Alter
                die codes. Non-Force characters see nothing here.

WEG D6 DIE CODES

  Shown as ND (e.g. 4D) or ND+P (e.g. 3D+2) where N = number of
  dice, P = pip bonus (1 or 2). Higher die codes = more capable.
  See `help dice` for the rolling mechanics.

EXAMPLES

  +sheet
  → Full character sheet.

  +sheet/brief
  → One-page summary — useful at a glance mid-session.

  +sheet/skills
  → All skills listed under their parent attribute.

  score
  → Same as +sheet (MUX-style alias).

CHEAT SHEET
  +sheet          = full character sheet
  +sheet/brief    = compact summary
  +sheet/skills   = skills only
  +sheet/combat   = wounds + soak + attack pools
  score / stats   = aliases for +sheet
