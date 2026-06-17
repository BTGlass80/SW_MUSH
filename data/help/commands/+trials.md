---
key: +trials
title: +Trials — Padawan Trial Progress
category: "Commands: Padawan-Master"
summary: View Trial completion status for a Padawan-Master bond. Shows which of the Five Trials have been passed and which remain.
aliases: [trials]
see_also: [+trial, +endorse, +authorize, +knight, +master, +padawan]
tags: [padawan, trials, jedi, promotion, command]
access_level: 1
examples:
  - cmd: "+trials"
    description: "(Padawan) Show your own Trial progress."
  - cmd: "+trials Anakin"
    description: "(Master) Show Anakin's Trial progress."
---

Display the Five Trials completion status for a Padawan-Master bond.
All five must be passed before a Padawan can be knighted.

SYNTAX

  +trials                    Padawan: your own progress.
                             Master with 1 Padawan: that Padawan's progress.
  +trials <padawan name>     Master: named Padawan's progress.

THE FIVE TRIALS

  Trials may be passed in any order. A Master records each pass
  via '+trial <name>' after the in-game event. Staff can use
  '@trial <name> = <padawan>' for override or correction.

    Trial of Skill    — combat or Force-power demonstration
    Trial of Courage  — solo mission in a hostile zone
    Trial of Flesh    — endurance or injury survival
    Trial of Spirit   — refusing dark-side temptation
    Trial of Insight  — perception or puzzle event

ENDORSEMENT

  Before attempting a Trial, a Padawan should have their Master's
  endorsement:
    - One-shot: '+endorse trials <padawan>' consumed on the next
      recorded +trial pass.
    - Standing: '+authorize <padawan> trials' grants a permanent
      endorsement (the Padawan can attempt any Trial without
      a fresh +endorse).

  Without any endorsement, Trial attempts auto-fail.

EXAMPLE OUTPUT

  +trials
  →  Trial of Skill       ✓  PASSED
  →  Trial of Courage     ·  pending
  →  Trial of Flesh       ·  pending
  →  Trial of Spirit      ·  pending
  →  Trial of Insight     ·  pending

AFTER ALL FIVE

  The Master uses '+knight <padawan>' to invoke the promotion
  ceremony (grants +1 Force Point and closes the bond with
  knighted status).

SEE ALSO

  +trial      Record a passed Trial (Master).
  +endorse    One-shot endorsement for next Trial attempt.
  +authorize  Standing authorization by category.
  +knight     Knight promotion ceremony.
  +master     Your Master's status (includes trial count).

CHEAT SHEET
  +trials          Padawan: my progress
  +trials <name>   Master: that Padawan's progress
