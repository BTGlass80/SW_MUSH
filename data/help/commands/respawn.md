---
key: respawn
title: Respawn / Bacta — Recovery from Death
category: "Commands: Medical"
summary: Return to life after being killed (respawn), or pay for a bacta tank treatment (bacta tank) to clear Wounded status.
aliases: [revive, bacta]
see_also: [+medical, stim, +healrate, +soak]
tags: [medical, combat, death, command]
access_level: 0
examples:
  - cmd: "respawn"
    description: "Return to life at the nearest safe location. You wake up Wounded."
  - cmd: "bacta tank"
    description: "Pay 500 credits for a bacta tank treatment — clears Wounded immediately."
---

Two commands handle recovery from serious wounds and death.

RESPAWN (after death)

  respawn       — return to life after being killed
  revive        — alias for respawn

  When your wound level reaches DEAD (Mortally Wounded → Dead),
  the game stops your combat actions. Type `respawn` to return
  to the nearest safe location.

  After respawning:
    • You wake up WOUNDED (not healthy)
    • Your equipment and credits are intact
    • You appear at the nearest safe respawn room
    • Seek a med-droid or a player medic to clear the Wounded status

BACTA TANK (clearing Wounded)

  bacta tank    — pay 500 credits for immediate Wounded → Healthy
  bacta         — alias (no argument needed)

  Available from any medical droid. You must be WOUNDED (not healthy
  and not dying) for the treatment to work. Cost is deducted from
  your credits automatically.

STIMS (medic assistance)

  A player with First Aid skill can administer stims:
    stim <player>                — basic stimpack (Easy difficulty)
    stim <player> with medpac   — heals one wound level

  You must type `stimaccept` to receive a stim from another player.
  Medpacs can be self-administered at a -1D penalty.

WOUND STATES

  Healthy → Stunned → Wounded → Incapacitated → Mortally Wounded → Dead

  Each step increases skill-check penalties. The bacta tank and
  medpacs heal one wound level each. Full healing takes time unless
  you visit a proper medical facility.

CHEAT SHEET

  respawn / revive   — return after death (wake up Wounded)
  bacta tank         — 500cr, Wounded → Healthy
  stim <player>      — medic treats another player
  stimaccept         — accept a stim from a medic
