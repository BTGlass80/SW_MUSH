---
key: +counsel
title: Counsel — Ease the Weight of War (Jedi)
category: "Commands: Force"
summary: Seek counsel to reduce your Weight of War by 10 points. Jedi-only. Available once per week. Requires a bonded Master (Padawans) or the Council Chamber (Knights and Masters).
aliases: [counsel]
see_also: ["+forcestatus", "+meditate", "+retreat", "+return", darkside, force, weight-of-war]
tags: [force, jedi, weight-of-war, command]
access_level: 0
examples:
  - cmd: "+counsel"
    description: "Seek counsel to reduce Weight of War by 10. (Cooldown: 1 week.)"
---

A Jedi path command for managing the Weight of War — the moral
toll of violence, death, and difficult choices in the Clone Wars.

JEDI ONLY

+counsel is only available to Force-sensitive characters following
the Jedi path. Non-Force characters receive "Only Jedi may seek
counsel for the Weight of War."

THE WEIGHT OF WAR

The Clone Wars grinds at the Jedi Code's ideals. Every use of
combat power, every life taken, every compromise against the
Light adds Weight. High Weight tilts a character toward the
Dark Side over time; keeping Weight manageable is part of living
as a Jedi in a galactic war.

See `+forcestatus` for your current Weight level and `+help
darkside` for how Weight interacts with Force Points and DSP.

EFFECT

-10 Weight of War on success. No Force Point cost.

The command is a narrative moment — a private meditation, a
conversation with your Master, or an audience with the Council.
It represents the internal and spiritual discipline that keeps
Jedi centered amid the war.

COOLDOWN — ONCE PER WEEK

You can seek counsel once every 7 days. The system tracks the
last time you used it. If you use it Monday, it's available again
the following Monday (rolling 7-day window, not calendar week).

AT-PEACE SHORTCIRCUIT

If your Weight is already at 0 (you're at peace), +counsel
succeeds but does nothing — "You are already at peace; counsel
finds no burden to ease." Your weekly slot is preserved for
later, after the war adds more weight.

REQUIREMENTS BY PATH

  As a Padawan with a bonded Master:
    - Your Master must be in the same room
    - Counsel is received through their guidance

  As a Knight or Master (no active bond):
    - You must be in the Council Chamber at the Jedi Temple
    - You receive counsel through the Council's presence or
      through solo meditation in the sacred space

If the requirement isn't met, +counsel explains what you need:
  "Your Master must be present to counsel a Padawan."
  "A Knight must seek counsel at the Council Chamber."

COMPANION COMMANDS

  +meditate       Reduce Weight slowly over time (free, anytime)
  +retreat        Extended leave — -2 Weight/day, cap 30
  +return         End retreat, apply accumulated decay
  +forcestatus    View your current Weight level and Force sheet

EXAMPLES

  (Padawan with Master Tundra in the room)
  +counsel
  → "In quiet words, Master Tundra helps you find your center.
     The burden of the war eases slightly.
     Weight of War: 35 → 25."

  (Knight, at the Council Chamber)
  +counsel
  → "The Force flows through the chamber. You release what
     you've carried. Weight of War: 18 → 8."

  (already at peace)
  +counsel
  → "You are already at peace; counsel finds no burden to ease.
     (Weekly availability preserved.)"

  (cooldown active)
  +counsel
  → "You have sought counsel recently. (Next available in 5d 3h)"

CHEAT SHEET
  +counsel      = -10 Weight (Jedi only, once/week)
  +meditate     = slow ongoing Weight reduction
  +retreat      = extended leave (-2/day, cap 30)
  +forcestatus  = current Weight + Force sheet
