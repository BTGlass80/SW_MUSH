---
key: +knight
title: +Knight — Knight Promotion Ceremony
category: "Commands: Padawan-Master"
summary: Master invokes the Knight promotion ceremony after all Five Trials are passed. Grants +1 Force Point and closes the bond with knighted status.
aliases: []
see_also: [+trials, +trial, +endorse, +authorize, +bond]
tags: [padawan, master, trials, knighting, promotion, jedi, command]
access_level: 1
examples:
  - cmd: "+knight Anakin"
    description: "Promote Anakin to Knight after all five Trials are recorded."
---

Invoke the Knight promotion ceremony for your Padawan. All five
Trials must be recorded as passed before this succeeds. Staff
use '@knight' to bypass the Trials gate for Council-fiat promotions
(battlefield knighting per Clone Wars canon).

SYNTAX

  +knight <padawan name>

REQUIREMENTS

  - You must be the Padawan's active Master.
  - All Five Trials must be recorded as PASSED (check '+trials').

EFFECTS ON SUCCESS

  - Bond status flips from 'active' to 'knighted'.
  - The Padawan gains +1 Force Point.
  - Promotion timestamp recorded on the bond.
  - Both characters receive a narrative-memory entry.
  - The Padawan is notified with a ceremonial message if online.

AFTER KNIGHTING

  The new Knight is now eligible (but not automatically authorized)
  to take a Padawan of their own using '+bond <name>'. The former
  Padawan-Master bond is closed; use '+padawan' / '+master' to confirm
  the bond shows as 'knighted' rather than active.

STAFF OVERRIDE

  '@knight <padawan>' bypasses the Five Trials gate. Used for
  emergency or story-driven promotions (Council fiat, field
  elevation during a campaign).

EXAMPLES

  +knight Anakin
  (all five Trials passed)
  → "You knight Anakin Skywalker. May the Force serve you well."
  → Anakin gains +1 Force Point.

  +knight Anakin
  (Trials incomplete)
  → "Anakin has only passed 3 of the Five Trials..."

SEE ALSO

  +trials     Check Trial completion before knighting.
  +trial      Record a passed Trial (Master).
  +endorse    Endorse a Trial attempt.
  +bond       Start a new bond (post-knighting).

CHEAT SHEET
  +knight <name>   promote to Knight (all 5 Trials required)
