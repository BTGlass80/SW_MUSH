---
key: +hunting
title: Hunting Log — Solo-PvE Grind Tally
category: "Commands: Character"
summary: Check your lifetime kill count against roaming hostiles, today's credit take vs the daily cap, and your next milestone hunter title.
aliases: [hunting, +huntlog, huntlog]
see_also: [+bounty, +title, +sheet, combat, +crew]
tags: [economy, credits, prestige, hunting, solo, command]
access_level: 0
examples:
  - cmd: "+hunting"
    description: "Show your kill tally, today's take, and your next milestone title."
  - cmd: "hunting"
    description: "Alias — same output."
---

Your hunting log tracks the ordinary roaming hostiles you've put down —
the guards, thugs, and pirates scattered across the galaxy that have their
own reward system. Defeating one pays a small credit trickle and counts
toward milestone hunter titles. It is the solo-play option when no one
else is on; RP and bounties are still the main road to advancement.

WHAT IS A HUNTABLE MOB?

Any roaming hostile NPC that is NOT already covered by another reward
hook (bounty, anomaly, wilderness spawn, DSP hunter, chain mission
enemy, or a vendor). Generic sentient guards, thugs, street pirates, and
similar NPCs in populated zones are the typical quarry.

REWARDS

  Credits: +15 cr per kill (BASE_REWARD) up to a daily soft cap of
  400 cr. Past the cap the reward drops to a token 3 cr per kill —
  you can keep grinding for prestige and titles, just not for income.

  **The daily cap resets at midnight UTC.**

  Note: Combat costs money (bacta, gear repair). A hard fight will
  typically cost more in supplies than the kill pays — grinding is
  deliberately break-even to slightly negative on difficult targets.
  The reward is the prestige track, not the income.

  Character Points: ZERO. Hunting grants no CP. The advancement system
  is RP + time-gated; grinding can never buy skill growth.

MILESTONE HUNTER TITLES

Lifetime kills unlock earned titles you can wear via +title wear <key>:

  Kills    Title key
  25       hunter
  100      seasoned_hunter
  500      master_hunter
  2,500    apex_hunter

Titles are permanent once earned and visible on +finger and +sheet.

THE +HUNTING DISPLAY

  ─────────────  HUNTING LOG  ─────────────
    Quarry felled (lifetime):  47
    Today's take: 255 / 400 cr
    Next milestone: 53 more to reach 100 felled.

Once you pass the daily cap the display notes it:
  Today's take: 432 cr  (daily 400 cr reached — only token rewards until tomorrow)

At 2,500 kills you've cleared every milestone:
  You have passed every hunting milestone (2500+). You stand at the apex.

CHEAT SHEET

  +hunting   — the only command; shows log, daily take, next title
  +title wear hunter  — equip your earned Hunter title (if you have it)

Sources: Base economy values are internal tuning knobs (T2.ECON.review).
