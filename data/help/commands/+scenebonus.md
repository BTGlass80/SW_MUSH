---
key: +scenebonus
title: SceneBonus — Scene Completion Award
category: "Commands: Social"
summary: Claim a tick award for completing a roleplay scene. The bonus scales with your pose count — more active participation earns more ticks.
aliases: [scenebonus, endscene, closescene, "+endscene"]
see_also: [+scene, +scenes, +cpstatus, +kudos, advancement]
tags: [social, roleplay, advancement, scene, command]
access_level: 0
examples:
  - cmd: "+scenebonus"
    description: "Claim a scene completion bonus (uses your logged pose count for the session)."
  - cmd: "scenebonus"
    description: "Same as +scenebonus (bare alias preserved)."
  - cmd: "endscene"
    description: "Flavor alias — 'close the scene' and claim the bonus."
---

Claim your scene completion bonus when you finish a roleplay session.
The game awards ticks (toward the next CP) scaled to how many poses
you contributed.

WHEN TO USE

After a collaborative RP scene wraps up — everyone has said their
goodbyes, the thread has a natural stopping point, and you're done
posing for this session. Use +scenebonus once per scene to capture
your contribution.

Using it after every pose or spamming it for tiny interactions
defeats the system — the bonus is meaningful only for genuine scenes.
Staff can see claim patterns.

TICK SCALING

The award scales with poses:
  1–3 poses     minimal award (a brief encounter)
  4–9 poses     standard scene award
  10–19 poses   extended scene — larger bonus
  20+ poses     full scene — maximum bonus tier

You can also manually pass a pose count if you're claiming for a
scene that wasn't tracked automatically:
  +scenebonus <count>
  e.g. `+scenebonus 15`

Staff / admins use the explicit count to award for scenes they
observed but weren't participants in.

COOLDOWN

You can only claim a scene bonus once per scene (tracked by
session). Wait until a scene actually concludes before claiming.
Claiming too rapidly or with trivially low pose counts may result
in a reduced award.

STACKING WITH KUDOS

If your scene partners also give you +kudos after the session, the
two stack — kudos awards 35 ticks on top of the scenebonus. An
exceptional collaborative scene where everyone kudoses each other
is the fastest path to CP advancement.

EXAMPLES

  (after a 15-pose scene at the cantina)
  +scenebonus
  → "Scene bonus claimed! Pose count: 15. Ticks awarded: 42."
  → "+cpstatus shows: 42 new ticks, now 167/200 for the week."

  +scenebonus 8
  → "Scene bonus claimed! Pose count: 8. Ticks awarded: 25."

CHEAT SHEET
  +scenebonus          = claim bonus (auto pose count)
  +scenebonus <n>      = claim with explicit pose count
  +cpstatus            = see ticks earned and CP total
  +kudos <name>        = also recognize your scene partners
