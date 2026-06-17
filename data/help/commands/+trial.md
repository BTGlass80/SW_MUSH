---
key: +trial
title: +Trial — Record a Passed Trial (Master)
category: "Commands: Padawan-Master"
summary: Master attests that their Padawan has passed one of the Five Trials. Staff use @trial for cross-Master attestation.
aliases: []
see_also: [+trials, +endorse, +knight, +authorize]
tags: [padawan, trials, jedi, promotion, command]
access_level: 1
examples:
  - cmd: "+trial skill"
    description: "Record that your sole Padawan passed the Trial of Skill."
  - cmd: "+trial courage Anakin"
    description: "Record that Anakin passed the Trial of Courage (multi-Padawan Masters)."
---

Record that a Padawan has passed one of the Five Trials. The Master
attests the pass in-character after the relevant in-game event. The
record is idempotent: re-attesting an already-passed Trial has no
additional effect.

SYNTAX

  +trial <trial name>               (Single-bond Masters) record for sole Padawan.
  +trial <trial name> <padawan>     (Multi-Padawan) specify which Padawan.

TRIAL NAMES

  skill, courage, flesh, spirit, insight
  (case-insensitive; "Trial of Skill" / "trial_of_skill" also accepted)

WHO CAN ATTEST

  - Masters use '+trial' for their own bonded Padawans.
  - Staff use '@trial <name> = <padawan>' for any Padawan,
    overrides, or corrections.

ENDORSEMENT CONSUMED

  Recording a Trial pass consumes any one-shot endorsement
  ('+endorse trials') on that Padawan. A standing authorization
  ('+authorize <padawan> trials') is NOT consumed.

EXAMPLES

  +trial skill
  → "You attest that <Padawan> has passed the Trial of Skill."

  +trial spirit Anakin
  → Anakin sees: "<Master> has recorded your Trial of Spirit as PASSED."
  → +trials now shows Spirit as ✓ PASSED.

  +trial skill   (already passed)
  → "The Trial of Skill is already recorded as passed — no change."

AFTER ALL FIVE

  Use '+knight <padawan>' when all five Trials show PASSED.

SEE ALSO

  +trials     View all Trial progress.
  +endorse    One-shot endorsement before a Trial.
  +authorize  Standing authorization by category.
  +knight     Knight promotion after all five Trials.

CHEAT SHEET
  +trial <trial>           record pass for sole Padawan
  +trial <trial> <name>    record pass for named Padawan
