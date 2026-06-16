---
key: +retreat
title: Retreat — Declare Extended Leave (Jedi)
category: "Commands: Force"
summary: Declare an extended leave of absence from the war. Accumulates -2 Weight of War per real-time day while in retreat, capped at -30 per retreat period. Use +return to end your retreat.
aliases: [retreat]
see_also: ["+return", "+counsel", "+forcestatus", "+meditate", force, weight-of-war]
tags: [force, jedi, weight-of-war, command]
access_level: 0
examples:
  - cmd: "+retreat"
    description: "Declare retreat from active duty. Weight decay begins accumulating."
  - cmd: "+return"
    description: "End your retreat and apply all accumulated Weight decay."
---

Withdraw from active duty and let time heal your wounds. A Jedi
in retreat accumulates Weight of War reduction passively while
away from the front lines.

JEDI ONLY

+retreat is only available to Force-sensitive Jedi characters.
Non-Force characters receive "Only Jedi may declare retreat from
the war."

MECHANICS

  - Decay rate: -2 Weight of War per real-time day
  - Cap: -30 maximum per retreat (15 days to reach the cap)
  - Accumulation: passive — you don't need to be online

The decay accumulates from the moment you declare retreat until
you end it with +return. Time spent offline counts — the system
records when you declared retreat and calculates elapsed days
when you return.

ENDING RETREAT

  +return applies the accumulated decay and brings you back to
  active duty. The decay is applied in a single step at the
  moment you return — not drip-fed over time.

You cannot declare a new retreat immediately after returning.
A cooldown prevents rapid retreat-return cycling to farm Weight
reduction.

CHECKING RETREAT STATUS

+retreat while already in retreat shows:
  "You are already in retreat (started ~3 day(s) ago). Use +return
   to end it."

+forcestatus shows your current Weight level. Calculate your
accumulated decay as: min(days_since_retreat × 2, 30).

COMBAT WHILE IN RETREAT

The retreat flag is currently informational — it marks your
status but does not block you from combat (a future update will
activate combat refusal for characters in formal retreat). For
now, retreat is a spiritual / social commitment.

INTENDED USE

  - Long offline period: declare retreat before stepping away for
    a week; return to 14 Weight off instead of entering the next
    session at peak weight
  - Narrative arc: a Jedi who witnessed something traumatic takes
    time at a temple to recover
  - Build management: a player who pushed hard on a combat-heavy
    arc uses retreat to bring Weight back down before the next arc

COMPARE WITH OTHER OPTIONS

  +counsel    -10 Weight, once/week, instantaneous
  +meditate   slow ongoing decay, anytime
  +retreat    large decay, passive, requires commitment period

EXAMPLES

  +retreat
  → "You withdraw from active duty. The galaxy will turn without
     you for a time.
     You are now in retreat. Use +return to end your retreat and
     apply accumulated decay (-2/day, cap -30)."

  (5 days later)
  +return
  → "You return to active duty. Retreat duration: 5 days.
     Weight of War: 40 → 30. (−10 accumulated; cap not reached)"

  (15 days later)
  +return
  → "You return to active duty. Retreat duration: 15 days.
     Weight of War: 40 → 10. (−30 accumulated; cap reached)"

CHEAT SHEET
  +retreat      = begin retreat (-2 Weight/day)
  +return       = end retreat (apply accumulated decay)
  +counsel      = -10 Weight now (weekly)
  +forcestatus  = current Weight level
