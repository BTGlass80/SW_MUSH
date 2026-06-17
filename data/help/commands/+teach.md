---
key: +teach
title: +Teach — Teach a Force Power to Your Padawan
category: "Commands: Padawan-Master"
summary: Master teaches a Force power to their bonded Padawan. Both must be in the same room. If the Padawan's relevant skill is below 1D, their Character Points are spent automatically.
aliases: []
see_also: [+learn, +spar, +powers, +padawan, +bond]
tags: [master, force, training, jedi, command]
access_level: 1
examples:
  - cmd: "+teach accelerate healing"
    description: "Teach your sole Padawan Accelerate Healing (both in same room)."
  - cmd: "+teach Anakin lightsaber combat"
    description: "Teach Anakin specifically (for Masters with multiple Padawans)."
---

Teach your bonded Padawan a Force power. Both of you must be in the
same room. If the Padawan's underlying Force skill is below 1D, their
Character Points are automatically spent to bring it to the minimum
before the power is granted.

SYNTAX

  +teach <power name>                 Sole-bond Masters.
  +teach <padawan name> <power name>  Multi-bond Masters (specify who).

REQUIREMENTS

  - You must have an active Padawan bond.
  - Both you and the Padawan must be in the same room.
  - You must know the power yourself (your own Force skill must be
    sufficient to teach it).
  - The Padawan must have a pending '+learn' request staged, OR you
    can teach proactively (the request is optional, not required).

WHAT HAPPENS

  1. The system checks you know the power and are in the same room.
  2. If the Padawan's relevant Force skill(s) are below 1D, their
     CP is spent to reach the 1D minimum.
  3. The teaching event is logged on the bond record.
  4. The Padawan is notified.

CP SPENDING

  The Padawan's CP covers the cost of raising prerequisite skills to
  1D minimum. If the Padawan already has the prerequisite skills,
  the teach is free (narrative only).

EXAMPLES

  +teach accelerate healing
  → "You teach <Padawan> the discipline of Accelerate Healing."
  → <Padawan> (if online) sees the notification.
  → If Padawan had Control below 1D: "(Padawan spent 2 CP to bring
    Control to 1D minimum.)"

  +teach Anakin lightsaber combat
  → Same, targeted to Anakin specifically.

SEE ALSO

  +learn       Padawan's request to learn a power.
  +spar        Training duel for CP gain.
  +powers      List all Force powers.
  +padawan     View your Padawan(s).

CHEAT SHEET
  +teach <power>            teach your sole Padawan
  +teach <padawan> <power>  teach a named Padawan (multi-bond Masters)
