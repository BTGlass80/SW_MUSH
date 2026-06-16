---
key: +cantina
title: +Cantina — Cantina Encounter Table (Staff)
category: "Commands: Staff"
summary: Roll the d66 Cantina Encounter Table and pose the result to the room. GM scene-seeding tool.
aliases: [+cantinaroll]
see_also: [+scene, emote, perform]
tags: [staff, gm, cantina, scene, d66, command]
access_level: 2
examples:
  - cmd: "+cantina"
    description: "Roll a random d66 cantina encounter and pose it to the room."
  - cmd: "+cantina 31"
    description: "Pose the specific d66 entry code 31 to the room."
---

Builder/staff tool: roll the d66 Cantina Encounter Table and broadcast
the resulting beat to the room as a posed scene texture. Based on WEG
Wretched Hive, era-translated for the Clone Wars setting. Use it to
seed a cantina scene with an organic detail — a shady patron, a sudden
fight breaking out, a droid making an unusual offer.

SYNTAX

  +cantina              Roll a random d66 entry and pose it here
  +cantinaroll          Alias — same as +cantina
  +cantina <code>       Pose a specific d66 entry (11–66)

ACCESS

  Builder-level access required. Players cannot use this command.

D66 CODES

  D66 means roll one die for the tens digit and one die for the units
  digit:  valid codes are 11–16, 21–26, 31–36, 41–46, 51–56, 61–66.
  There are 36 distinct beats.

  +cantina 11    — First entry in the table
  +cantina 66    — Last entry in the table
  +cantina       — Random (equal probability across all 36)

WORLD EVENT INTERACTION

  When a CANTINA_BRAWL world event is active, a random +cantina roll
  automatically surfaces the brawl beat. Explicit code selection
  (+cantina 31, etc.) is unaffected by this modifier.

EXAMPLES

  +cantina
  → GM rolls random cantina beat; room sees a posed narrative line.

  +cantina 24
  → Posts the specific d66 code 24 beat to the room.

SEE ALSO

  +scene   Start a formal scene log in the room.
  perform  Player command to earn credits performing in a cantina.

CHEAT SHEET
  +cantina              random d66 cantina beat → posed to room
  +cantina <11–66>      specific d66 entry → posed to room
  (Builder+ only)
