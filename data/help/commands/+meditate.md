---
key: +meditate
title: +Meditate — Jedi Meditation
category: "Commands: Force"
summary: Meditate at the Jedi Temple to reduce your Weight of War by 5, spending 1 Force Point. Jedi only; once per day; Temple only.
aliases: [meditate]
see_also: [+forcestatus, +powers, +threat, +soak]
tags: [meditate, force, jedi, weight-of-war, command]
access_level: 0
examples:
  - cmd: "+meditate"
    description: "Meditate to reduce your Weight of War by 5 (costs 1 Force Point)."
---

Meditate at the Coruscant Jedi Temple to ease your burden under the
Weight of War. Costs 1 Force Point and reduces your Weight by 5.
Jedi-only, Temple-only, and usable once per day.

SYNTAX

  +meditate

REQUIREMENTS

  - You must be a Jedi (Force-sensitive with appropriate skills).
  - You must be inside the Coruscant Jedi Temple (any room within
    the temple zone qualifies: archives, council chamber, meditation
    chamber, main gate, etc.).
  - You must have at least 1 Force Point.
  - Your Weight of War must be above 0.
  - Once per 24 hours (real time).

WHAT IS WEIGHT OF WAR?

  Weight of War (WoW) is a measure of the psychological and ethical
  burden a Jedi carries from decisions made during the Clone Wars.
  It accumulates from difficult choices, combat, and morally
  ambiguous events. High Weight has narrative consequences and
  affects certain Force interactions.

  Meditation is one of the few active ways to reduce Weight.
  The full -5 applies even if your Weight is below 5 (it clamps
  at 0). You spend 1 FP regardless.

EXAMPLES

  +meditate
  (standing in the Temple meditation chamber)
  → Spends 1 Force Point. Weight reduced by 5.
  → You may not meditate again for 24 hours.

  +meditate
  (outside the Temple)
  → "You must be at the Jedi Temple to meditate in this way."

  +meditate
  (Weight already 0)
  → "You are already at peace. No Weight to ease."
    (No FP spent; cooldown not consumed.)

SEE ALSO

  +forcestatus   Check your current Force Points.
  +powers        List available Force powers.
  +threat        Your threat level in contested regions.

CHEAT SHEET
  +meditate   at Temple, costs 1 FP, -5 Weight, once/day
