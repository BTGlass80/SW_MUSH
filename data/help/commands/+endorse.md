---
key: +endorse
title: +Endorse — Endorse a Padawan's Trial Attempt
category: "Commands: Padawan-Master"
summary: Master grants a one-shot endorsement for the Padawan's next Trial attempt. Without endorsement, Trial attempts auto-fail.
aliases: []
see_also: [+trial, +trials, +authorize, +knight]
tags: [padawan, trials, endorsement, jedi, command]
access_level: 1
examples:
  - cmd: "+endorse trials Anakin"
    description: "Endorse Anakin for their next Trial attempt."
---

Grant your Padawan a one-shot endorsement for their next Trial attempt.
Without any endorsement, Trial attempts auto-fail. The endorsement is
consumed when the next '+trial' pass is recorded.

SYNTAX

  +endorse trials <padawan name>

ONE-SHOT VS STANDING

  - One-shot (+endorse): consumed on the next +trial record. The
    Master must re-endorse before each subsequent Trial attempt.
  - Standing (+authorize <padawan> trials): a permanent grant that
    replaces the need to re-endorse each time. See +authorize.

WHAT HAPPENS

  - The endorsement flag is written to the Padawan's record.
  - The Padawan sees a real-time notification if online.
  - When the Master later records a Trial pass via '+trial', the
    endorsement is cleared automatically.

REQUIREMENTS

  - You must be the active Master for the named Padawan.
  - The Padawan must have an active bond.

EXAMPLES

  +endorse trials Anakin
  → "You endorse Anakin for their next Trial attempt."
  → Anakin sees: "Obi-Wan has endorsed your next Trial attempt."

  (After Anakin attempts the Trial and Master records it:)
  +trial skill Anakin
  → Endorsement is consumed; a fresh '+endorse' is needed for
    the next Trial.

SEE ALSO

  +authorize    Standing authorization (replaces repeated +endorse).
  +trial        Record a passed Trial.
  +trials       View Trial progress.
  +knight       Promotion after all five Trials.

CHEAT SHEET
  +endorse trials <padawan>   one-shot Trial endorsement (consumed on next pass)
