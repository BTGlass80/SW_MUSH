---
key: +return
title: Return — End Retreat and Apply Weight Decay
category: "Commands: Force"
summary: End your Jedi retreat and return to active duty. Applies the accumulated Weight of War decay (-2/day while in retreat, capped at -30).
aliases: []
see_also: ["+retreat", "+counsel", "+forcestatus", "+meditate", force, weight-of-war]
tags: [force, jedi, weight-of-war, command]
access_level: 0
examples:
  - cmd: "+return"
    description: "End your retreat and apply accumulated Weight of War decay."
  - cmd: "+return"
    description: "(after 5 days in retreat) Apply -10 Weight of War (-2/day × 5 days)."
---

End an active retreat and return to duty. The Weight of War decay
accumulated during your absence is applied immediately.

This command is the partner to +retreat. It does nothing unless
you previously used +retreat to declare a leave of absence.

MECHANICS

  Accumulated decay = min(days_since_retreat × 2, 30)

  Days in retreat:  1     2     5     10    15+
  Weight reduced:  -2    -4   -10   -20   -30 (cap)

The cap of 30 is the maximum benefit from a single retreat period
regardless of how long you stay away. Longer retreats (beyond 15
days) don't earn more decay than the cap allows.

WHAT HAPPENS ON RETURN

  1. The system calculates elapsed real-time days since +retreat
  2. Decay amount is computed (capped at 30)
  3. Weight of War is reduced by that amount (floor 0)
  4. Retreat state is cleared
  5. You receive a summary: duration, Weight before/after

After returning you can engage in normal activity — combat,
missions, the full range of Jedi commands. A cooldown period
prevents immediately declaring another retreat.

JEDI ONLY

Like +retreat, +return is only for Force-sensitive Jedi characters.

IF YOU'RE NOT IN RETREAT

Using +return without an active retreat shows:
  "You are not currently in retreat."

COMPARE WITH +COUNSEL AND +MEDITATE

  +counsel    instant -10 Weight, weekly cooldown, no retreat needed
  +meditate   slow passive decay, no commitment period
  +retreat    larger decay, but you must commit to the leave period
  +return     ends the retreat and collects the decay

EXAMPLES

  (3 days after +retreat)
  +return
  → "You return to active duty. Retreat duration: 3 days.
     Weight of War: 35 → 29. (−6 accumulated)"

  (12 days after +retreat)
  +return
  → "You return to active duty. Retreat duration: 12 days.
     Weight of War: 50 → 26. (−24 accumulated)"

  (16 days after +retreat — cap hit)
  +return
  → "You return to active duty. Retreat duration: 16 days.
     Weight of War: 30 → 0. (−30 accumulated; cap reached)"

  (not in retreat)
  +return
  → "You are not currently in retreat."

CHEAT SHEET
  +return       = end retreat + apply decay (min(days×2, 30))
  +retreat      = declare retreat (begins -2/day accumulation)
  +forcestatus  = current Weight + Force sheet
