---
key: +spar
title: +Spar — Training Duel with Bond Partner
category: "Commands: Padawan-Master"
summary: "Initiate a training lightsaber duel with your bonded Master or Padawan. Both participants earn 1 CP. Cooldown: once per 24 hours per bonded pair."
aliases: []
see_also: [+learn, +teach, +master, +padawan, +cpstatus]
tags: [padawan, master, training, spar, jedi, command]
access_level: 1
examples:
  - cmd: "+spar"
    description: "Initiate a training spar with your bond partner (must be in same room)."
---

Initiate a narrative training lightsaber duel with your bonded Master
or Padawan. Both participants earn 1 Character Point. The CP reward
refreshes every 24 hours per bonded pair.

SYNTAX

  +spar

REQUIREMENTS

  - You must have an active Padawan-Master bond (as either side).
  - Your bond partner must be in the same room.
  - At least 24 hours must have passed since your last CP-rewarding
    spar with this partner.

LAUNCH-SCOPE NOTE

  At launch, +spar is a narrative event with CP reward. The full
  non-lethal combat-loop integration (training mode in the combat
  engine) is a post-launch follow-up. The spar description is
  generated as flavor text; no actual dice rolls determine a winner.

WHAT HAPPENS

  1. Both PCs receive 1 Character Point immediately.
  2. The spar is logged on the bond record (training_log).
  3. A 24-hour cooldown starts for this bonded pair.

COOLDOWN DISPLAY

  If you spar too soon after the last session, the command shows
  the remaining hours and minutes before the next CP-awarding spar.
  You can still RP a spar at any time — just no CP until the
  cooldown clears.

EXAMPLES

  +spar
  → (both in same room, 24h+ since last spar)
  → Both you and your partner gain 1 CP.
  → Bond training log updated.

  +spar
  → (too soon)
  → "You sparred too recently to gain training value. (8h 30m before
    next CP-awarding spar.)"

SEE ALSO

  +learn       Request Force power training.
  +teach       Teach a Force power.
  +cpstatus    Check your current Character Points.
  +padawan     View your Padawan(s).

CHEAT SHEET
  +spar   training duel with bond partner (1 CP each, 24h cooldown)
